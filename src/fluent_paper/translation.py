"""Resumable paragraph translation with the official local PLaMo 3 MLX backend."""
import hashlib
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace

MODEL='pfnet/plamo-3-translate-2b'
VERSION='ja-v1'
PROTECTED=re.compile(r'\$\$[\s\S]*?\$\$|(?<!\\)\$[^\n$]+(?<!\\)\$|\[(?:-?@)[^\]]+\]|@paper-ref-\d+')


def model_name():return os.environ.get('FLUENT_PAPER_TRANSLATION_MODEL',MODEL)

def fingerprint(text,model=None):
    return hashlib.sha256(json.dumps([VERSION,model or model_name(),text],ensure_ascii=False).encode()).hexdigest()

def save(path,value):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2));temporary.replace(path)

def protect(text):
    values=[]
    def replace(m):
        values.append(m[0]);return f'ZXKEEP{len(values)-1}XZ'
    return PROTECTED.sub(replace,text),values

def restore(text,values):
    for i,value in enumerate(values):
        token=f'ZXKEEP{i}XZ'
        if text.count(token)!=1:raise ValueError('Translation did not preserve a math/reference marker')
        text=text.replace(token,value)
    if re.search(r'ZXKEEP\d+XZ',text):raise ValueError('Unexpected translation marker')
    return text


def translate_paper(folder,model=None):
    import fcntl
    model=model or model_name()
    with (folder/'translation.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        inputs=json.loads((folder/'translation-input.json').read_text())
        path=folder/'translation-ja.json'
        cache=json.loads(path.read_text()) if path.exists() else {'entries':{}}
        cache.update(model=model,version=VERSION,status='processing',total=sum(r['kind']!='equation' for r in inputs),error=None)
        translator=None
        def infer(value):
            nonlocal translator
            if not re.search(r'[A-Za-z]',value):return value
            if len(value)>3500:
                chunks=[];current=''
                for word in value.split(' '):
                    if len(current)+len(word)>3500 and current:chunks.append(current);current=''
                    current+=(' ' if current else '')+word
                if current:chunks.append(current)
                if len(chunks)>1:return ' '.join(infer(chunk) for chunk in chunks)
            if translator is None:
                from plamo_translate.servers.mlx.plamo3_runtime import Plamo3Translator
                translator=Plamo3Translator(model,'4bit')
            messages=[SimpleNamespace(content='input lang=English\n'+value),SimpleNamespace(content='output lang=Japanese\n')]
            result=list(translator.stream(messages,max_tokens=4096))
            if result[-1].finish_reason!='stop':raise ValueError('Translation reached the output token limit')
            output=''.join(r.text for r in result).strip()
            if not output:raise ValueError('Empty translation')
            return output
        completed=0;save(path,cache)
        try:
            for row in inputs:
                if row['kind']=='equation':continue
                value=row['markdown'];key=fingerprint(value,model)
                if key not in cache['entries']:
                    # Leave already Japanese paragraphs in Japanese, including embedded English terms.
                    if len(re.findall(r'[\u3040-\u30ff]',value))>10:
                        output=value;method='already-ja'
                    else:
                        masked,protected=protect(value)
                        try:output=restore(infer(masked),protected);method='paragraph'
                        except ValueError:
                            # Never silently lose or alter a formula. Retry prose runs while
                            # copying each protected span exactly at its original position.
                            parts=PROTECTED.split(value);tokens=PROTECTED.findall(value);pieces=[]
                            for i,part in enumerate(parts):
                                pieces.append(infer(part) if part.strip() else part)
                                if i<len(tokens):pieces.append(tokens[i])
                            output=''.join(pieces);method='protected-spans'
                    cache['entries'][key]={'text':output,'method':method,'source_id':row['id']}
                completed+=1;cache['completed']=completed;save(path,cache)
                print(f'Translation {completed}/{cache["total"]}',flush=True)
            cache['status']='ready';save(path,cache)
        except Exception as exc:
            cache.update(status='failed',error=str(exc));save(path,cache);raise
        finally:
            if translator is not None:
                del translator
                import mlx.core as mx
                mx.clear_cache()
    return cache
