"""Loopback-only UI. One lifespan-owned worker services browser/API uploads."""
from contextlib import asynccontextmanager
import html
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from urllib.parse import urlparse
from fastapi import FastAPI, UploadFile, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from . import cli

@asynccontextmanager
async def lifespan(app):
    cli.database().close()
    log=(cli.ROOT/'worker.log').open('a')
    process=subprocess.Popen([sys.executable,'-m','fluent_paper.cli','work'],stdout=log,stderr=log,start_new_session=True)
    yield
    if process.poll() is None:
        os.killpg(process.pid,signal.SIGTERM)
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
    log.close()

app=FastAPI(lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','testserver'])

@app.middleware('http')
async def local_writes(request:Request,call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        if origin and urlparse(origin).netloc!=request.headers.get('host'):
            return JSONResponse({'detail':'Cross-origin writes are disabled'},status_code=403)
        if request.headers.get('sec-fetch-site')=='cross-site':return JSONResponse({'detail':'Cross-site writes are disabled'},status_code=403)
    return await call_next(request)

@app.get('/',response_class=HTMLResponse)
def index():
    with cli.database() as db:rows=db.execute("SELECT * FROM papers WHERE status!='excluded' ORDER BY rowid DESC").fetchall()
    items=[]
    for r in rows:
        title=html.escape(r['title']);status=r['status']
        if status=='ready':title=f'<a href="/papers/{r["id"]}/index.html">{title}</a>'
        retry=f'<form method="post" action="/api/papers/{r["id"]}/retry"><button>Retry</button></form>' if status=='failed' else ''
        items.append(f'<li><div>{title}</div><small>{html.escape(status)}</small>{retry}</li>')
    refresh='<script>setTimeout(()=>location.reload(),8000)</script>' if any(r['status'] in ('queued','processing') for r in rows) else ''
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Fluent Paper</title><style>body{max-width:950px;margin:60px auto;padding:24px;font:16px system-ui;background:#fff;color:#252525}h1{font-size:25px;font-weight:600}ul{list-style:none;padding:0;margin-top:35px}li{padding:20px 0;border-top:1px solid #eee;display:flex;gap:20px;align-items:center}li div{flex:1}small{color:#777;font-size:12px}a{color:inherit;text-decoration:none}a:hover{text-decoration:underline}button{background:#fff;border:1px solid #ccc;border-radius:4px;padding:6px 12px;cursor:pointer}form{display:flex;gap:12px;align-items:center}input{max-width:75%}</style><h1>Library</h1><form action="/api/papers" method="post" enctype="multipart/form-data"><input aria-label="PDF" type="file" accept="application/pdf" name="file" required><button>Add paper</button></form><ul>'''+''.join(items)+'</ul>'+refresh+'</html>'

@app.post('/api/papers')
async def upload(file:UploadFile,request:Request):
    data=await file.read(100*1024*1024+1)
    if len(data)>100*1024*1024:raise HTTPException(413)
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/Path(file.filename or 'paper.pdf').name
        path.write_bytes(data)
        try:key=cli.add(path)
        except ValueError as exc:raise HTTPException(400,str(exc))
    if 'application/json' in request.headers.get('accept',''):return JSONResponse({'id':key,'status':'queued'},status_code=202)
    return RedirectResponse('/',status_code=303)

@app.post('/api/papers/{key}/retry')
def retry(key:str):
    with cli.database() as db:
        changed=db.execute("UPDATE papers SET status='queued',error=NULL WHERE id=? AND status='failed'",(key,)).rowcount
    if not changed:raise HTTPException(409,'Only failed jobs can be retried')
    return RedirectResponse('/',status_code=303)

@app.get('/api/papers')
def papers():
    with cli.database() as db:return [dict(r) for r in db.execute("SELECT * FROM papers WHERE status!='excluded'")]

@app.get('/papers/{key}/{asset:path}')
def asset(key:str,asset:str):
    if len(key)!=24 or any(c not in '0123456789abcdef' for c in key):raise HTTPException(404)
    base=(cli.ROOT/key/'site/_site').resolve();path=(base/asset).resolve()
    if not path.is_relative_to(base) or not path.is_file() or any(p.startswith('.') for p in Path(asset).parts):raise HTTPException(404)
    return FileResponse(path)
