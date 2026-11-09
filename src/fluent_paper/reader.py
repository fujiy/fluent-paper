"""Build a static Quarto reader from the preserved block representation."""
from copy import deepcopy
from pathlib import Path
import html
import json
import re
import shutil
import subprocess

ASSETS = Path(__file__).parent
VISUAL = {'image', 'chart', 'table'}
SKIP = {'header', 'footer', 'page_number', 'doc_title'}

def text_content(value):
    if isinstance(value, str): return value
    if isinstance(value, list): return ''.join(text_content(x) for x in value)
    if isinstance(value, dict): return text_content(value.get('content', ''))
    return ''

def safe_markdown(text):
    # Preserve TeX math; disallow raw scripts, executable cells and remote images.
    import nh3
    math = []
    def mask(m):
        math.append(m[0]); return f'MATHPLACEHOLDER{len(math)-1}END'
    text = re.sub(r'\$\$[\s\S]*?\$\$|(?<!\\)\$[^\n$]+(?<!\\)\$', mask, text)
    text = nh3.clean(text, tags={'table','thead','tbody','tr','td','th','br','sub','sup'}, attributes={'td':{'rowspan','colspan'},'th':{'rowspan','colspan'}})
    text = re.sub(r'```\{[^\n]*', '```text', text)
    def image_reference(m):
        path=m[2]
        return m[0] if path.startswith('images/') and '..' not in Path(path).parts and not path.startswith('/') else '[Image: '+m[1]+']'
    text = re.sub(r'!\[([^]]*)\]\(([^)]+)\)',image_reference,text)
    text = text.replace('{{<', '{{&lt;').replace('{{%', '{{&#37;')
    for i, value in enumerate(math): text = text.replace(f'MATHPLACEHOLDER{i}END',value)
    return text

def render_block(raw, block):
    from mineru.parser.base import ParseResult
    data = deepcopy(raw)
    data['pages'] = [{'page_idx':0,'blocks':[block]}]
    return safe_markdown(ParseResult.from_dict(data).markdown())

def build_reader(folder, fallback_title):
    from .provenance import normalize
    source = folder / 'parsed/middle_json.json'
    raw = json.loads(source.read_text())
    doc = normalize(source, folder / 'document.json')
    site = folder / 'site-building'
    if site.exists(): shutil.rmtree(site)
    site.mkdir(exist_ok=True)
    shutil.copytree(ASSETS/'vendor',site/'vendor')
    # Copy only selected rendering assets, never parser archives or logs.
    if (folder / 'parsed/images').exists(): shutil.copytree(folder / 'parsed/images', site / 'images', dirs_exist_ok=True)
    shutil.copytree(ASSETS / 'margin-layout', site / '_extensions/margin-layout', dirs_exist_ok=True)
    shutil.copyfile(folder / 'source.pdf', site / 'source.pdf')
    title = next((text_content(b['original']['content']) for b in doc['blocks'] if b['type']=='doc_title'), fallback_title)
    corrections = json.loads((folder / 'corrections.json').read_text()) if (folder / 'corrections.json').exists() else {'changes':[]}
    changes = {x['id']:x for x in corrections['changes'] if x.get('accepted')}
    from .structure import restore
    from .references import References
    import os
    structure=restore(doc,folder,os.environ.get('FLUENT_PAPER_STRUCTURE_MODEL','qwen3:4b'))
    blocks=structure['blocks']
    refs=References(blocks);refs.write(site)
    validation=json.loads((folder/'math-validation.json').read_text()) if (folder/'math-validation.json').exists() else {'errors':[]}
    math_errors={(e['page'],e.get('index')) for e in validation['errors']}
    body=[]
    for b in blocks:
        if b['type']=='ref_text':continue
        original=deepcopy(b['original'])
        if b['id'] in changes and len(b['sources'])==1:
            original['content']=changes[b['id']]['after']
        if b['type']=='paragraph_title':
            if re.match(r'^(References|Bibliography|参考文献)\s*$',text_content(original),re.I):continue
            heading=deepcopy(original);heading['type']='text';heading.pop('level',None)
            value=render_block(raw,heading).strip().replace('\n',' ')
            body.append('#'*b['level']+' '+value+' {#sec-'+b['id']+'}')
            continue
        equation_image=original.get('image_path') if b['type']=='equation' else None
        bad_equation=b['type']=='equation' and (b['page'],original.get('index')) in math_errors
        if b['type']=='equation' and b.get('xref'):
            latex=re.sub(r'\\tag\s*\{[^{}]*\}','',original['content'])
            md='$$\n'+latex+'\n$$ {#'+b['xref']+'}'
        elif b['type'] in VISUAL and b.get('xref'):
            caption_parts=[];content_parts=[]
            for child in original.get('content',[]):
                if child.get('type','').endswith('caption'):
                    c=deepcopy(child);c['type']='text';caption_parts.append(render_block(raw,c).strip())
                elif child.get('image_path'):content_parts.append('![]('+child['image_path']+')')
                elif child.get('type','').endswith('body'):
                    content_parts.append(render_block(raw,original).strip())
            caption=' '.join(caption_parts)
            caption=re.sub(r'^\s*\*{0,2}(?:Fig(?:ure)?\.?|Table|図|表)\s*'+re.escape(b['label'][1])+r'[.:]?\s*\*{0,2}\s*','',caption,flags=re.I)
            caption=re.sub(r'第\s*'+re.escape(b['label'][1])+r'[図表]\s*','',caption,count=1)
            md='::: {#'+b['xref']+'}\n\n'+'\n\n'.join(content_parts)+'\n\n'+refs.convert(caption)+'\n\n:::'
        else:md=render_block(raw,original).strip()
        if not md:continue
        if b['type']=='text':md=refs.convert(md)
        sources=b['sources']
        source_link=' '.join(f'<button class="source-button" data-block="{q["id"]}" aria-label="View source, page {q["page"]}">p. {q["page"]}</button>' for q in sources)
        classes=['paper-block']
        if b['type']=='text':classes.append('prose-block')
        attributes=f'data-source-page="{b["page"]}"'
        if equation_image:attributes+=' data-equation-image="'+html.escape(equation_image,quote=True)+'"'
        if bad_equation and equation_image:
            attributes+=' data-equation-fallback="true"'
            b['corrections'].append({'rule':'invalid extracted TeX; original equation image shown','accepted':True})
        suspect=b['type'] in VISUAL and any(c.get('type','').endswith('caption') and len(text_content(c))>200 and not re.match(r'\s*(?:Fig(?:ure)?\.?|Table|図|表)\s*\d',text_content(c),re.I) for c in original.get('content',[]))
        if suspect:b['corrections'].append({'rule':'ambiguous long caption retained in main column','accepted':True})
        if not suspect and (b['type'] in VISUAL or b['type']=='page_footnote'):
            classes.append('margin-item')
            targets=b.get('scope_ids',[])
            if targets:attributes+=' margin-for="'+' '.join(t+'-scope' for t in targets)+'"'
        if b['type']=='text':body.append(':::::: {#'+b['id']+'-scope .margin-scope}')
        body.append('::::: {#'+b['id']+' .'+ ' .'.join(classes)+' '+attributes+'}\n\n'+md+'\n\n'+source_link+'\n\n:::::')
        if b['type']=='text':body.append('::::::')
    if refs.entries:body.append('## References {#references}\n\n::: {#refs}\n:::')
    doc['reading_blocks']=blocks
    (folder/'document.json').write_text(json.dumps(doc, ensure_ascii=False, indent=2))
    # Small source metadata only; not original text or library paths.
    (site/'sources.js').write_text('window.FluentSources = '+json.dumps({b['id']:{'page':b['page'],'bbox':b['bbox']} for b in doc['blocks']}))
    source_images=site/'pages';source_images.mkdir(exist_ok=True)
    import pypdfium2 as pdf
    pdfdoc=pdf.PdfDocument(folder/'source.pdf')
    for index in range(len(pdfdoc)):
        dest=source_images/f'{index+1}.jpg'
        if not dest.exists(): pdfdoc[index].render(scale=1.5).to_pil().save(dest,quality=82)
    pdfdoc.close()
    (site/'_quarto.yml').write_text('''project:
  type: website
  resources:
    - source.pdf
    - sources.js
    - pages/
    - vendor/
filters:
  - margin-layout
format:
  html:
    toc: true
    toc-title: Contents
    toc-location: left
    toc-depth: 4
    theme: cosmo
    css: reader.css
    include-after-body: reader.html
    html-math-method:
      method: mathjax
      url: vendor/mathjax/tex-chtml.js
    link-external-newwindow: true
    citations-hover: true
bibliography: references.json
csl: paper.csl
link-citations: true
nocite: |
  @*
execute:
  enabled: false
''')
    attribution = json.loads((folder/'publication.json').read_text()) if (folder/'publication.json').exists() else None
    notice=''
    if attribution:
        notice=f'\n<div class="attribution">{html.escape(attribution["citation"])} · <a href="{html.escape(attribution["source"],quote=True)}">Publisher</a> · <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>. Reconstructed from PDF; layout and extraction corrections differ from the original.</div>\n'
    (site/'index.qmd').write_text('---\ntitle: '+json.dumps(title)+'\nlang: en\n---\n\n<div class="reader-tools"><a href="source.pdf">Original PDF</a><button id="toggle-sources">Source links</button><button id="show-figures">Figures</button></div>\n'+notice+'\n\n'+'\n\n'.join(body))
    for name in ['reader.css','reader.html']: shutil.copyfile(ASSETS/name,site/name)
    with (folder/'build.log').open('w') as log:
        subprocess.run(['quarto','render','index.qmd'],cwd=site,stdout=log,stderr=subprocess.STDOUT,check=True)
    # Equation fallback images are referenced by data attributes, which Quarto's
    # resource scanner does not discover. Keep them available offline too.
    if (site/'images').exists():shutil.copytree(site/'images',site/'_site/images',dirs_exist_ok=True)
    output=site/'_site/index.html'
    markup=output.read_text()
    markup=re.sub(r'<script[^>]+src="https://cdnjs.cloudflare.com/polyfill/[^"]+"[^>]*></script>', '', markup)
    from bs4 import BeautifulSoup
    parsed=BeautifulSoup(markup,'html.parser')
    # Native Quarto resolves anchors; restore source numbering after citeproc.
    # Its current custom-label list support fails on multi-character labels.
    for b in blocks:
        key=b.get('xref')
        if not key:continue
        number=b.get('equation_label') or b['label'][1]
        for link in parsed.select('a.quarto-xref'):
            if link.get('href')=='#'+key:
                label=link.select_one('.quarto-xref') or link
                label.clear();label.append(number)
        target=parsed.find(id=key)
        if target and key.startswith('eq-'):
            for node in list(target.find_all(string=True)):
                if r'\tag{' in node:
                    node.replace_with(re.sub(r'\\tag\s*\{[^{}]*\}',lambda _:r'\tag{'+number+'}',str(node)))
        elif target:
            caption=target.select_one('.quarto-float-caption')
            if caption:
                for node in caption.find_all(string=True):
                    if re.search(r'(Figure|Table)\s*\d+',str(node)):
                        node.replace_with(re.sub(r'((?:Figure|Table)\s*)\d+',lambda m:m[1]+number,str(node),count=1));break
    for block in parsed.select('[data-equation-fallback="true"]'):
        math=block.select_one('.math')
        if math:
            image=parsed.new_tag('img',src=block['data-equation-image'],alt='Original equation')
            math.replace_with(image)
    output.write_text(str(parsed))
    published=folder/'site'
    if published.exists():shutil.rmtree(published)
    site.rename(published)
    return title
