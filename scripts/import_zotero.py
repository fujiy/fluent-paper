"""Import a bounded private evaluation corpus without changing Zotero."""
import json
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import unquote, urlparse
from fluent_paper.cli import add, ROOT
import pypdfium2 as pdf
base = 'http://127.0.0.1:23119/api/users/0'
def get(route):
    with urlopen(base + route) as response: return json.load(response)
selected = []
for item in get('/items/top?limit=100&itemType=journalArticle'):
    for child in get('/items/' + item['key'] + '/children'):
        if child['data'].get('contentType') != 'application/pdf': continue
        try:
            with urlopen(base + '/items/' + child['key'] + '/file/view/url') as response:
                raw = response.read().decode()
            try: raw = json.loads(raw)
            except ValueError: pass
            path = Path(unquote(urlparse(raw).path))
            document=pdf.PdfDocument(path)
            pages=len(document);document.close()
            if pages>80: continue
            key = add(path)
            selected.append({'id':key, 'zotero':item['key'], 'title':item['data']['title']})
            break
        except Exception as exc: print(type(exc).__name__)
    if len(selected) >= 12: break
(ROOT / 'evaluation.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2))
print('Imported', len(selected), 'private PDFs')
