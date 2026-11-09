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
    site = folder / 'site'
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
    blocks = doc['blocks']
    references = {}
    for b in blocks:
        if b['type']=='ref_text':
            number=re.match(r'\s*(\d+)[.)]',text_content(b['original']))
            if number:
                references[b['id']]=[t['id']+'-scope' for t in blocks if t['type']=='text' and re.search(r'\[[^\]]*\b'+number[1]+r'\b[^\]]*\]',text_content(t['original']))]
            continue
        if b['type'] not in VISUAL: continue
        caption = ' '.join(text_content(c) for c in b['original'].get('content',[]) if c['type'].endswith('caption'))
        match = re.search(r'(?:Fig(?:ure)?\.?|Table)\s*(\d+)',caption,re.I)
        if match:
            kind = 'Table' if caption.lstrip().lower().startswith('table') else 'Fig'
            targets=[]
            pattern = re.compile(r'\b'+kind+r'(?:ure)?s?\.?\s*'+match[1]+r'\b',re.I)
            for t in blocks:
                if t['type']=='text' and pattern.search(text_content(t['original'])): targets.append(t['id']+'-scope')
            references[b['id']] = targets
    validation=json.loads((folder/'math-validation.json').read_text()) if (folder/'math-validation.json').exists() else {'errors':[]}
    math_errors={(e['page'], e.get('index')) for e in validation['errors']}
    body=[]
    for b in blocks:
        if b['type'] in SKIP: continue
        original = deepcopy(b['original'])
        if b['id'] in changes:
            original['content']=changes[b['id']]['after']
            b['corrections'].append(changes[b['id']])
        equation_image=original.get('image_path') if b['type']=='equation' else None
        bad_equation=(b['page'],original.get('index')) in math_errors
        if b['type']=='equation':
            latex=original.get('content','')
            bad_equation=bad_equation or len(re.findall(r'\\tag\s*\{',latex))>1
        if bad_equation and equation_image:
            md=f'![Original equation]({equation_image})'
            b['corrections'].append({'rule':'invalid extracted TeX; original equation image shown','accepted':True})
        else: md = render_block(raw, original).strip()
        if not md: continue
        source_link=f'<button class="source-button" data-block="{b["id"]}" aria-label="View source, page {b["page"]}">p. {b["page"]}</button>'
        classes='paper-block'
        attributes=f'data-source-page="{b["page"]}"'
        if equation_image: attributes+=' data-equation-image="'+html.escape(equation_image,quote=True)+'"'
        suspect = b['type'] in VISUAL and any(c.get('type','').endswith('caption') and len(text_content(c))>200 and not re.match(r'\s*(?:Fig(?:ure)?\.?|Table|図|表)\s*\d',text_content(c),re.I) for c in b['original'].get('content',[]))
        if suspect:
            b['corrections'].append({'rule':'ambiguous long caption retained in main column','accepted':True})
        if not suspect and (b['type'] in VISUAL or b['type']=='page_footnote' or (b['type']=='ref_text' and references.get(b['id']))):
            classes+=' margin-item'
            targets=references.get(b['id'],[])
            if targets: attributes+=' margin-for="'+' '.join(targets)+'"'
        if b['type']=='text': body.append(f'::: {{#{b["id"]}-scope .margin-scope}}')
        body.append(f':::: {{#{b["id"]} .'+classes.replace(' ', ' .')+' '+attributes+'}\n\n'+md+'\n\n'+source_link+'\n\n::::')
        if b['type']=='text': body.append(':::')
    (folder/'document.json').write_text(json.dumps(doc, ensure_ascii=False, indent=2))
    # Small source metadata only; not original text or library paths.
    (site/'sources.js').write_text('window.FluentSources = '+json.dumps({b['id']:{'page':b['page'],'bbox':b['bbox']} for b in blocks}))
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
    theme: cosmo
    css: reader.css
    include-after-body: reader.html
    html-math-method:
      method: mathjax
      url: vendor/mathjax/tex-chtml.js
    link-external-newwindow: true
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
    output=site/'_site/index.html'
    markup=output.read_text()
    markup=re.sub(r'<script[^>]+src="https://cdnjs.cloudflare.com/polyfill/[^"]+"[^>]*></script>', '', markup)
    output.write_text(markup)
    return title
