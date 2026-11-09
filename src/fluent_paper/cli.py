"""Local, resumable PDF ingestion. Private data lives outside the checkout."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

ROOT = Path(os.environ.get('FLUENT_PAPER_HOME', Path.home() / 'Library/Application Support/fluent-paper'))

def database():
    ROOT.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(ROOT / 'library.sqlite', timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS papers (id TEXT PRIMARY KEY, title TEXT, status TEXT, error TEXT)')
    return db

def add(path):
    path = Path(path)
    data = path.read_bytes()
    if not data.startswith(b'%PDF-'):
        raise ValueError('Expected a PDF file')
    key = hashlib.sha256(data).hexdigest()[:24]
    with database() as db:
        folder = ROOT / key
        folder.mkdir(exist_ok=True)
        if not (folder / 'source.pdf').exists():
            (folder / 'source.pdf').write_bytes(data)
        db.execute('INSERT OR IGNORE INTO papers VALUES (?, ?, ?, ?)', (key, path.stem, 'queued', None))
    return key

def process(key):
    with database() as db:
        row = db.execute('SELECT * FROM papers WHERE id=?', (key,)).fetchone()
        if not row:
            raise ValueError('Unknown paper')
        if row['status'] == 'ready':
            return
        claimed = db.execute("UPDATE papers SET status='processing', error=NULL WHERE id=? AND status IN ('queued','failed')", (key,)).rowcount
        if not claimed:
            return
    folder = ROOT / key
    try:
        env = dict(os.environ, MINERU_TELEMETRY_DISABLED='1', MINERU_LLM_AIDED_FEATURES_TITLE_LEVELING='false', MINERU_LLM_AIDED_FEATURES_CROSS_PAGE_TABLE_CELL_MERGE='false')
        with (folder / 'parse.log').open('w') as log:
            subprocess.run([str(Path(sys.executable).parent / 'mineru-kit'), 'parse', str(folder / 'source.pdf'), '-o', str(folder / 'parsed'), '--format', 'zip'], env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        build(key, row['title'])
        status, error = 'ready', None
    except Exception as exc:
        status, error = 'failed', str(exc)
    with database() as db:
        db.execute('UPDATE papers SET status=?,error=? WHERE id=?', (status, error, key))

def build(key, title):
    folder = ROOT / key
    # MinerU output is retained verbatim; the adapter is deliberately isolated.
    import zipfile
    for archive in (folder / 'parsed').rglob('*.zip'):
        with zipfile.ZipFile(archive) as z:
            for member in z.infolist():
                target = (folder / 'parsed' / member.filename).resolve()
                if not target.is_relative_to((folder / 'parsed').resolve()):
                    raise ValueError('Unsafe archive path')
            z.extractall(folder / 'parsed')
    candidates = list((folder / 'parsed').rglob('*.md'))
    if not candidates:
        raise ValueError('MinerU produced no Markdown; inspect parse.log')
    source = max(candidates, key=lambda p: p.stat().st_size)
    from .provenance import normalize
    normalize(source.parent / 'middle_json.json', folder / 'document.json')
    site = folder / 'site'
    site.mkdir(exist_ok=True)
    shutil.copytree(source.parent, site, dirs_exist_ok=True)
    shutil.copytree(Path(__file__).parent / 'margin-layout', site / '_extensions/margin-layout', dirs_exist_ok=True)
    shutil.copyfile(folder / 'source.pdf', site / 'source.pdf')
    (site / '_quarto.yml').write_text('project:\n  type: website\nfilters:\n  - margin-layout\nformat:\n  html:\n    toc: true\n    toc-location: left\n    theme: cosmo\n    css: reader.css\n    embed-resources: false\n    include-after-body: reader.html\n    html-math-method: mathjax\nexecute:\n  enabled: false\n')
    # Disable raw HTML and executable fences in untrusted extracted content.
    content = source.read_text()
    content = re.sub(r'(?m)^(!\[[^\n]*?\]\([^\n]+\))$', r'::: {.margin-item}\n\1\n:::', content)
    content = content.replace('<', '&lt;').replace('```{', '```text ')
    (site / 'index.qmd').write_text('---\ntitle: ' + json.dumps(title) + '\n---\n\n[Original PDF](source.pdf){.source-link}\n\n' + content)
    (site / 'reader.css').write_text('body{background:#fff;color:#222}main{font-family:Georgia,serif;line-height:1.75}h1,h2,h3,nav{font-family:system-ui,sans-serif}figure img{cursor:zoom-in} .source-link{font:14px system-ui} figure img{max-width:100%} @media print{figure{float:none!important;margin:1em 0!important}}')
    (site / 'reader.html').write_text('<script>document.querySelectorAll("main img").forEach(i=>{i.addEventListener("click",()=>{const d=document.createElement("dialog");const c=i.cloneNode();c.style="max-width:90vw;max-height:85vh";d.append(c);d.addEventListener("click",()=>d.remove());document.body.append(d);d.showModal()})});</script>')
    subprocess.run(['quarto', 'render', 'index.qmd'], cwd=site, check=True, stdout=subprocess.DEVNULL)

def worker(once=False, inbox=None):
    while True:
        if inbox:
            for file in Path(inbox).glob('*.pdf'):
                try: add(file)
                except (OSError, ValueError): pass
        with database() as db:
            rows = db.execute("SELECT id FROM papers WHERE status='queued'").fetchall()
        for row in rows:
            process(row['id'])
        if once: return
        time.sleep(3)

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    ingest = sub.add_parser('add'); ingest.add_argument('pdf', nargs='+')
    work = sub.add_parser('work'); work.add_argument('--once', action='store_true'); work.add_argument('--inbox')
    sub.add_parser('list')
    retry = sub.add_parser('retry'); retry.add_argument('id')
    serve = sub.add_parser('serve'); serve.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if args.command == 'add':
        for pdf in args.pdf: print(add(pdf))
    elif args.command == 'work': worker(args.once, args.inbox)
    elif args.command == 'list':
        with database() as db:
            print(json.dumps([dict(x) for x in db.execute('SELECT * FROM papers')], indent=2))
    elif args.command == 'retry':
        with database() as db: db.execute("UPDATE papers SET status='queued' WHERE id=? AND status!='processing'", (args.id,))
    elif args.command == 'serve':
        import uvicorn
        from .server import app
        uvicorn.run(app, host='127.0.0.1', port=args.port)

if __name__ == '__main__': main()
