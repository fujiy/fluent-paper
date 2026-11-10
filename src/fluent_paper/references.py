"""Quarto cross-references and native citeproc bibliography from extracted labels."""
import json
import re
from .structure import text, figure_label

NUMBER=r'\d+(?:\.\d+)*[a-z]?'

def slug(value):return re.sub(r'[^a-z0-9]+','-',value.lower()).strip('-')

class References:
    def __init__(self,blocks):
        self.figures={};self.tables={};self.equations={};self.entries=[];self.numeric={};self.author_year={}
        for b in blocks:
            label=figure_label(b)
            if label:
                kind,num=label;mapping=self.tables if kind=='tbl' else self.figures
                if num not in mapping:mapping[num]=kind+'-'+slug(num);b['xref']=mapping[num]
            if b['type']=='equation':
                tags=re.findall(r'\\tag\s*\{([^{}]+)\}',text(b['original']))
                if tags:
                    num=tags[-1].strip()
                    if num not in self.equations:self.equations[num]='eq-'+slug(num);b['xref']=self.equations[num];b['equation_label']=num
        refs=[]
        for b in blocks:
            if b['type']!='ref_text':continue
            value=text(b['original']).strip()
            if not re.search(r'\b(?:18|19|20)\d{2}[a-z]?\b',value) and refs:
                refs[-1]['text']+=' '+value;refs[-1]['sources'].extend(b['sources']);continue
            refs.append({'text':value,'sources':list(b['sources'])})
        self.numbered=sum(bool(re.match(r'^\s*\[?\d+[\].)]\s*',r['text'])) for r in refs)>len(refs)/2
        for i,r in enumerate(refs):
            value=r['text'];m=re.match(r'^\s*\[?(\d+)[\].)]\s*',value)
            number=m[1] if m else None
            if m:value=value[m.end():]
            years=re.findall(r'\b((?:18|19|20)\d{2}[a-z]?)\b',value)
            year=years[-1] if years else None
            paren=re.search(r'\(((?:18|19|20)\d{2})[a-z]?\)',value)
            if paren:year=paren[1]
            prefix=re.split(r':|\((?:18|19|20)\d{2}',value)[0]
            surnames=re.findall(r'(?:^|,\s*|\band\s+)([A-ZÀ-ÖØ-Þ][\wÀ-ÿ’\'-]*(?:\s+[A-Z][\w’\'-]*)?),\s*[A-Z]\.',prefix)
            if not surnames:surnames=[value.split(',')[0].strip()]
            key=f'paper-ref-{i+1}';entry={'id':key,'type':'article-journal','title':value,'call-number':f'{i:05d}','citation-label':number or str(i+1),'author':[{'family':n} for n in surnames]}
            if year:entry['issued']={'date-parts':[[int(year[:4])]]}
            self.entries.append(entry)
            if number:self.numeric[number]=key
            if year:
                pair=(surnames[0],year);self.author_year.setdefault(pair,[]).append(key)
        self.source_references=refs

    def write(self,site):
        (site/'references.json').write_text(json.dumps(self.entries,ensure_ascii=False,indent=2))
        if self.numbered:
            citation='<layout prefix="[" suffix="]" delimiter=", "><text variable="citation-label"/></layout>'
            label='<text variable="citation-label" suffix=". "/>'
        else:
            citation='''<layout prefix="(" suffix=")" delimiter="; "><group delimiter=", "><names variable="author"><name form="short" and="text" delimiter=", "/><et-al/></names><date variable="issued"><date-part name="year"/></date></group></layout>'''
            label=''
        (site/'paper.csl').write_text('''<?xml version="1.0" encoding="utf-8"?>
<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text" default-locale="en-US"><info><title>Preserved paper references</title><id>https://fujiy.github.io/fluent-paper/style</id><updated>2026-11-10T00:00:00+00:00</updated></info><citation et-al-min="3" et-al-use-first="1">'''+citation+'''</citation><bibliography><sort><key variable="call-number"/></sort><layout>'''+label+'''<text variable="title"/></layout></bibliography></style>''')

    def convert(self,markdown):
        def numeric(m):
            values=[]
            for part in re.split(r'\s*,\s*',m[1]):
                ran=re.fullmatch(r'(\d+)\s*[-–]\s*(\d+)',part)
                if ran and int(ran[2])-int(ran[1])<=30:values.extend(str(n) for n in range(int(ran[1]),int(ran[2])+1))
                else:values.append(part.strip())
            if values and all(n in self.numeric for n in values):return '['+'; '.join('@'+self.numeric[n] for n in values)+']'
            return m[0]
        # Standalone superscript citation marks are common in Japanese papers.
        # A real power such as $x^{2}$ or $10^{3}$ is never matched.
        def superscript(m):
            value=m[1].replace(r'\sim','-').replace('～','-')
            match=re.fullmatch(r'([\d\s,–-]+)\)?',value)
            converted=numeric(match) if match else ''
            return converted if converted.startswith('[@') else m[0]
        markdown=re.sub(r'\$\s*\^\s*\{([\d\s,()–~～\\sim-]+)\}\s*\$',superscript,markdown)
        markdown=re.sub(r'(\*{1,2})((?:Figures?|Figs?|Tables?)\.?)\1',r'\2',markdown,flags=re.I)
        markdown=re.sub(r'((?:Figures?|Figs?|Tables?)\.?\s+)\$(\d+[a-z]?)\$',r'\1\2',markdown,flags=re.I)
        protected=[]
        def hide(m):protected.append(m[0]);return f'PROTECTEDMATH{len(protected)-1}END'
        value=re.sub(r'\$\$[\s\S]*?\$\$|(?<!\\)\$[^\n$]+(?<!\\)\$',hide,markdown)
        for names,mapping in [(r'(?:Figures?|Figs?)\.?',self.figures),(r'Tables?',self.tables)]:
            pattern=re.compile(r'\b('+names+r')\s+('+NUMBER+r'(?:\s*(?:,|and|–|-)\s*'+NUMBER+r')*)',re.I)
            def group(m):
                def number(n):
                    key=n[0] if n[0] in mapping else re.sub(r'[a-z]$','',n[0])
                    return '[-@'+mapping[key]+']'+n[0][len(key):] if key in mapping else n[0]
                return m[1]+' '+re.sub(NUMBER,number,m[2])
            value=pattern.sub(group,value)
        value=re.sub(r'第\s*(\d+)\s*([図表])',lambda m:'第[-@'+(self.tables if m[2]=='表' else self.figures)[m[1]]+']'+m[2] if m[1] in (self.tables if m[2]=='表' else self.figures) else m[0],value)
        # Bare parenthesized equation numbers also occur after "from", "using", etc.
        def equation(m):
            num=m[1]
            return '([-@'+self.equations[num]+'])' if num in self.equations else m[0]
        value=re.sub(r'\(('+NUMBER+r')\)',equation,value)
        value=re.sub(r'\[([\d\s,–-]+)\]',numeric,value)
        # Match exact first-author + year only; ambiguous same-author/year stays unchanged.
        for (name,year),keys in self.author_year.items():
            if len(keys)!=1:continue
            author=re.escape(name)+r'(?:\s+et\s+al\.?|\s+(?:and|&)\s+[\wÀ-ÿ’\'-]+)?'
            value=re.sub(r'\(\s*'+author+r',?\s*'+year+r'\s*\)', '[@'+keys[0]+']',value)
            value=re.sub(r'\b'+author+r'\s*\(\s*'+year+r'\s*\)', '@'+keys[0],value)
            value=re.sub(r'\b'+author+r',\s*'+year+r'\b','@'+keys[0],value)
        # Already parenthesized citation groups become one native citeproc group.
        value=re.sub(r'\((@paper-ref-\d+(?:\s*[;,]\s*@paper-ref-\d+)*)\)',lambda m:'['+m[1].replace(',',';')+']',value)
        for i,v in enumerate(protected):value=value.replace(f'PROTECTEDMATH{i}END',v)
        return value
