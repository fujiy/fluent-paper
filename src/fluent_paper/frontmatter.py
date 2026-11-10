"""Extract verified author names and abstract blocks for Quarto's title block."""
import re
from .structure import Decisions, text


def clean(value):
    if isinstance(value,list):return ''.join(clean(x) for x in value)
    if isinstance(value,dict):
        if 'superscript' in value.get('styles',[]):return ''
        return clean(value.get('content',''))
    return value if isinstance(value,str) else ''


def extract(blocks,folder,model):
    candidates=[]
    for b in blocks:
        if b['page']>2:break
        t=clean(b['original']).strip()
        if b['type']=='paragraph_title' and re.match(r'^(?:1\.?\s|I\.\s|Introduction|緒言|はじめに)',t,re.I):break
        if b['type'] in ('text','paragraph_title') and len(t)<8000:candidates.append({'id':b['id'],'text':t})
    answer=Decisions(folder,model).ask('frontmatter',
        'Extract author names verbatim from the supplied paper front matter. Do not include degrees, author marker numbers, affiliations or correspondence. Return authors [{name,source_id}] and abstract_ids (IDs of complete abstract paragraphs, not its separate heading). Use only supplied names and IDs. Do not infer missing authors or abstracts.',candidates) if candidates and model else {}
    byid={b['id']:b for b in blocks};allowed={b['id']:b['text'] for b in candidates}
    authors=[];author_ids=set()
    for item in answer.get('authors',[]):
        if not isinstance(item,dict):continue
        name=item.get('name','').strip();key=item.get('source_id')
        if key in allowed and len(name)>2 and re.sub(r'\s+',' ',name) in re.sub(r'\s+',' ',allowed[key]):
            if name not in [a['name'] for a in authors]:authors.append({'name':name})
            author_ids.add(key)
    abstract_ids=[key for key in answer.get('abstract_ids',[]) if key in allowed and byid[key]['type']=='text']
    if not abstract_ids:
        abstract_ids=[b['id'] for b in candidates if re.match(r'^(Abstract|概要|要旨)[.．:：\s]',b['text'],re.I)]
    # A labeled abstract is a mechanical boundary; do not let a missed model
    # selection hide its heading while leaving the abstract in the body.
    labeled=[];inside=False
    for b in candidates:
        if re.fullmatch(r'(Abstract|概要|要旨)[.．:：\s]*',b['text'],re.I):inside=True;continue
        if not inside:continue
        if byid[b['id']]['type']=='paragraph_title' or re.match(r'^(Key\s*words?|Keywords?|Received|Accepted)\b',b['text'],re.I):break
        if byid[b['id']]['type']=='text':labeled.append(b['id'])
    if labeled:abstract_ids=labeled
    hidden=set(abstract_ids)
    # Only suppress a name line when no substantial additional text is discarded.
    for key in author_ids:
        remainder=allowed[key]
        for author in authors:remainder=remainder.replace(author['name'],'')
        if not re.sub(r'\band\b|[\W\d_]','',remainder,flags=re.I):hidden.add(key)
    for b in candidates:
        if re.fullmatch(r'(Abstract|概要|要旨)[.．:：\s]*',b['text'],re.I):hidden.add(b['id'])
    return {'authors':authors,'abstract_ids':abstract_ids,'hidden_ids':sorted(hidden)}
