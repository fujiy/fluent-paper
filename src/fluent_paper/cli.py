"""Local, resumable PDF ingestion. Private data lives outside the checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path
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
    if path.stat().st_size > 100*1024*1024: raise ValueError('PDF exceeds 100 MiB')
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
        if not (folder / 'parsed/source.zip').exists():
            with (folder / 'parse.log').open('w') as log:
                subprocess.run([str(Path(sys.executable).parent / 'mineru-kit'), 'parse', str(folder / 'source.pdf'), '-o', str(folder / 'parsed'), '--format', 'zip'], env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        title = build(key, row['title'])
        status, error = 'ready', None
    except Exception as exc:
        status, error = 'failed', str(exc)
    with database() as db:
        db.execute('UPDATE papers SET status=?,error=? WHERE id=?', (status, error, key))
        if status == 'ready': db.execute('UPDATE papers SET title=? WHERE id=?', (title, key))

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
    if os.environ.get('FLUENT_PAPER_LLM'):
        from .correction import correct
        correct(folder, os.environ['FLUENT_PAPER_LLM'])
    from .reader import build_reader
    return build_reader(folder, title)

def worker(once=False, inbox=None):
    import fcntl
    database().close()
    with (ROOT / 'worker.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another worker already owns this library')
        # Owning the exclusive lock proves no cooperating worker is active.
        with database() as db:
            db.execute("UPDATE papers SET status='queued' WHERE status='processing'")
        while True:
            if inbox:
                for file in Path(inbox).glob('*'):
                    if file.suffix.lower() != '.pdf' or time.time()-file.stat().st_mtime < 3: continue
                    try: add(file)
                    except (OSError, ValueError): pass
            with database() as db:
                rows = db.execute("SELECT id FROM papers WHERE status='queued'").fetchall()
            for row in rows: process(row['id'])
            if once: return
            time.sleep(3)

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    ingest = sub.add_parser('add'); ingest.add_argument('pdf', nargs='+')
    work = sub.add_parser('work'); work.add_argument('--once', action='store_true'); work.add_argument('--inbox')
    sub.add_parser('list')
    rebuild = sub.add_parser('rebuild'); rebuild.add_argument('id', nargs='?', default='all')
    correct = sub.add_parser('correct'); correct.add_argument('id'); correct.add_argument('--model', default='qwen3:4b')
    retry = sub.add_parser('retry'); retry.add_argument('id')
    serve = sub.add_parser('serve'); serve.add_argument('--port', type=int, default=8790)
    args = parser.parse_args()
    if args.command == 'add':
        for pdf in args.pdf: print(add(pdf))
    elif args.command == 'work': worker(args.once, args.inbox)
    elif args.command == 'correct':
        from .correction import correct
        correct(ROOT / args.id, args.model)
    elif args.command == 'rebuild':
        with database() as db:
            rows = db.execute("SELECT id,title FROM papers WHERE status='ready'").fetchall() if args.id=='all' else db.execute('SELECT id,title FROM papers WHERE id=?',(args.id,)).fetchall()
        for row in rows:
            title=build(row['id'],row['title'])
            with database() as db: db.execute('UPDATE papers SET title=? WHERE id=?',(title,row['id']))
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
