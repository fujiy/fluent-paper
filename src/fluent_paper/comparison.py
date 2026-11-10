"""Assemble static comparison data; no PDF or prose is sent to a cloud API."""
from copy import deepcopy
import json
import re
import subprocess
from bs4 import BeautifulSoup
from .translation import fingerprint,model_name


def clean_node(node):
    node=deepcopy(node)
    for child in node.select('.source-button,.anchorjs-link,.margin-layout-toolbar'):child.decompose()
    for item in [node,*node.find_all(True)]:
        item.attrs.pop('id',None)
        item.attrs.pop('data-compare-id',None)
    return str(node)


def build_data(soup,inputs,folder,page_sizes,refs):
    path=folder/'translation-ja.json'
    cache=json.loads(path.read_text()) if path.exists() else {'entries':{},'status':'missing'}
    translations={};chunks=[]
    # Resolve protected native references using labels already present in the reader.
    labels={}
    for citation in soup.select('.citation'):
        for key in citation.get('data-cites','').split():
            link=citation.select_one('a[href="#ref-'+key+'"]')
            if link:labels[key]=link.get_text(' ',strip=True)
    numbers={b['xref']:(b.get('equation_label') or b['label'][1]) for b in json.loads((folder/'document.json').read_text()).get('reading_blocks',[]) if b.get('xref')}
    def reference(m):
        keys=re.findall(r'@([\w-]+)',m[0]);links=[]
        for key in keys:
            if key in numbers:links.append('['+numbers[key]+'](#'+key+')')
            elif key.startswith('paper-ref-'):links.append('['+labels.get(key,key.removeprefix('paper-ref-'))+'](#ref-'+key+')')
        return '; '.join(links) if links else m[0]
    for row in inputs:
        entry=cache['entries'].get(fingerprint(row['markdown']))
        if not entry:continue
        from .reader import safe_markdown
        value=safe_markdown(entry['text'])
        value=re.sub(r'\[-?@[^\]]+\]|@paper-ref-\d+',reference,value)
        chunks.append('::: {#translated-'+row['id']+'}\n\n'+value+'\n\n:::')
    if chunks:
        result=subprocess.run(['quarto','pandoc','--from=markdown','--to=html','--mathjax'],input='\n\n'.join(chunks),text=True,capture_output=True,check=True)
        rendered=BeautifulSoup(result.stdout,'html.parser')
        translations={n['id'].removeprefix('translated-'):''.join(str(c) for c in n.contents) for n in rendered.select('[id^="translated-"]')}
    rows=[]
    for row in inputs:
        node=soup.find(id=row['id'])
        if node is None:continue
        if node.name=='section':node=node.find(re.compile(r'^h[1-6]$')) or node
        node['data-compare-id']=row['id']
        rows.append({**{k:row[k] for k in ['id','kind','sources']},'html':clean_node(node),'translation_html':translations.get(row['id'])})
    complete=all(row['translation_html'] for row in rows if row['kind']!='equation')
    state=cache.get('status','missing')
    if state=='ready' and not complete:state='stale'
    return {'rows':rows,'pages':page_sizes,'translation_status':state,'model':cache.get('model',model_name())}
