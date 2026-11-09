"""Stable source references and structural diagnostics for MinerU 4 outputs."""
import hashlib
import json
from collections import Counter
from pathlib import Path

def normalize(source: Path, output: Path):
    raw = json.loads(source.read_text())
    blocks = []
    for page in raw['pages']:
        for index, block in enumerate(page['blocks']):
            blocks.append({'id': f'p{page["page_idx"]+1}-b{index}', 'page':page['page_idx']+1,
                           'bbox': block.get('bbox'), 'type':block['type'], 'original':block,
                           'corrections':[]})
    document = {'version':1, 'source_schema':raw.get('schema_version'), 'blocks':blocks,
                'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2))
    report = {'pages':len(raw['pages']), 'blocks':len(blocks), 'types':dict(Counter(b['type'] for b in blocks)),
              'missing_bbox':[b['id'] for b in blocks if not b['bbox']], 'human_review':'pending'}
    output.with_name('quality.json').write_text(json.dumps(report, indent=2))
    return document
