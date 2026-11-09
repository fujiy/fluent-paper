import html
import tempfile
from pathlib import Path
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from .cli import ROOT, database, add

app = FastAPI()

@app.get('/', response_class=HTMLResponse)
def index():
    with database() as db:
        rows = db.execute('SELECT * FROM papers ORDER BY rowid DESC').fetchall()
    body = ''.join(f'<li><a href="/papers/{r["id"]}/index.html">{html.escape(r["title"])}</a> <small>{html.escape(r["status"])}</small></li>' for r in rows)
    return '<!doctype html><html lang="en"><meta charset="utf-8"><title>Fluent Paper</title><style>body{max-width:900px;margin:60px auto;padding:24px;font:16px system-ui;background:white;color:#222}li{margin:20px 0}small{color:#666}a{color:inherit}</style><h1>Library</h1><form action="/api/papers" method="post" enctype="multipart/form-data"><input aria-label="PDF" type="file" accept="application/pdf" name="file" required><button>Add paper</button></form><ul>'+body+'</ul></html>'

@app.post('/api/papers')
async def upload(file: UploadFile):
    data = await file.read(100 * 1024 * 1024 + 1)
    if len(data) > 100 * 1024 * 1024: raise HTTPException(413)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / Path(file.filename or 'paper.pdf').name
        path.write_bytes(data)
        try: add(path)
        except ValueError as exc: raise HTTPException(400, str(exc))
    return RedirectResponse('/', status_code=303)

@app.get('/api/papers')
def papers():
    with database() as db: return [dict(r) for r in db.execute('SELECT * FROM papers')]

@app.get('/papers/{key}/{asset:path}')
def asset(key: str, asset: str):
    if len(key) != 24 or any(c not in '0123456789abcdef' for c in key): raise HTTPException(404)
    base = (ROOT / key / 'site' / '_site').resolve()
    path = (base / asset).resolve()
    if not path.is_relative_to(base) or not path.is_file(): raise HTTPException(404)
    return FileResponse(path)
