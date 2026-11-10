"""Check private rebuilt readers without exporting paper text or identifiers."""
from collections import Counter
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit
from bs4 import BeautifulSoup
from fluent_paper.cli import ROOT, database

summary=Counter()
with database() as db:rows=db.execute("SELECT id FROM papers WHERE status='ready'").fetchall()
for row in rows:
    folder=ROOT/row['id'];site=folder/'site/_site'
    soup=BeautifulSoup((site/'index.html').read_text(),'html.parser')
    structure=json.loads((folder/'reading-structure.json').read_text())
    ids=[e['id'] for e in soup.select('[id]')]
    assert len(ids)==len(set(ids)), 'Duplicate IDs'
    for link in soup.select('a[href^="#"]'):
        assert not link['href'][1:] or unquote(link['href'][1:]) in ids, 'Broken fragment'
    for e in soup.select('img[src],script[src],link[rel=stylesheet][href]'):
        path=e.get('src') or e.get('href');url=urlsplit(path)
        if not url.scheme and not url.netloc:assert (site/unquote(url.path)).is_file(), 'Missing local asset'
    for item in soup.select('[data-margin-for],[margin-for]'):
        for target in (item.get('data-margin-for') or item.get('margin-for')).split():assert target in ids,'Missing margin scope'
    sources=json.loads((site/'sources.js').read_text().split('=',1)[1])
    for button in soup.select('.source-button'):assert button['data-block'] in sources,'Missing original source'
    assert not soup.select('.prose-block .quarto-float'), 'Figure nested inside prose'
    for block in structure['blocks']:
        if block.get('xref','').startswith('eq-'):
            target=soup.find(id=block['xref'])
            assert target is not None, 'Missing equation target'
            if not target.find('img'):assert '\\tag{'+block['equation_label']+'}' in target.get_text(), 'Changed equation number'
    comparison=site/'comparison-data.js'
    if comparison.exists():
        data=json.loads(comparison.read_text().split('=',1)[1])
        assert all(soup.select_one('[data-compare-id="'+row['id']+'"]') for row in data['rows']), 'Missing comparison paragraph'
        if data['translation_status']=='ready':assert all(row['translation_html'] for row in data['rows'] if row['kind']!='equation'),'Incomplete translation'
        summary['comparison_rows']+=len(data['rows'])
        summary['translated_rows']+=sum(bool(row['translation_html']) for row in data['rows'])
    summary['papers']+=1;summary['paragraph_joins']+=len(structure['aliases'])
    summary['citation_mentions']+=len(soup.select('.citation a[role=doc-biblioref]'))
    summary['cross_reference_links']+=len(soup.select('a.quarto-xref'))
    summary['llm_errors']+=structure['llm_errors']
    summary['figures_with_scopes']+=sum(bool(b.get('scope_ids')) for b in structure['blocks'])
print(json.dumps(summary,indent=2))
(ROOT/'reader-validation.json').write_text(json.dumps(summary,indent=2))
