"""Private corpus audit; no paper text is written into the repository."""
from collections import Counter
from pathlib import Path
import json,re
import pypdfium2 as pdf
from fluent_paper.cli import ROOT,database
from fluent_paper.reader import text_content

def tokens(t):return Counter(re.findall(r'[a-z]{2,}|[\u3040-\u30ff\u4e00-\u9fff]',t.lower()))
reports=[]
with database() as db: rows=db.execute("SELECT id,status FROM papers WHERE status='ready'").fetchall()
for row in rows:
 folder=ROOT/row['id'];raw=json.loads((folder/'parsed/middle_json.json').read_text());source=pdf.PdfDocument(folder/'source.pdf')
 missing=[];page_scores=[];counts=Counter();suspect=[]
 for page in raw['pages']:
  idx=page['page_idx'];blocks=page['blocks']
  for b in blocks:
   counts[b['type']]+=1
   if b['type'] in ('chart','image','table'):
    for child in b.get('content',[]):
     if child['type'].endswith('caption'):
      t=text_content(child)
      if len(t)>200 and not re.match(r'\s*(?:Fig(?:ure)?\.?|Table|図|表)\s*\d',t,re.I):suspect.append({'page':idx+1,'index':b.get('index'),'type':'possible_body_as_caption'})
  source_text=source[idx].get_textpage().get_text_range()
  extracted=' '.join(text_content(b) for b in blocks)
  expected=tokens(source_text);actual=tokens(extracted)
  coverage=sum((expected&actual).values())/sum(expected.values()) if expected else None
  page_scores.append({'page':idx+1,'text_token_coverage':round(coverage,3) if coverage is not None else None,'source_text_tokens':sum(expected.values())})
  if not blocks:missing.append(idx+1)
 report={'id':row['id'],'pdf_pages':len(source),'parsed_pages':len(raw['pages']),'empty_pages':missing,'blocks':dict(counts),'page_checks':page_scores,'suspected_caption_errors':suspect,'note':'Token overlap is a text-layer diagnostic, not semantic or equation accuracy. Scans require visual review.'}
 (folder/'evaluation-report.json').write_text(json.dumps(report,indent=2));reports.append(report)
 print(row['id'],len(source),len(raw['pages']),counts['equation'],'equations',len(suspect),'suspect captions')
 source.close()
(ROOT/'evaluation-report.json').write_text(json.dumps(reports,indent=2))
