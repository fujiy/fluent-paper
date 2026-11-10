import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fluent_paper.translation import protect,restore,fingerprint
from fluent_paper.frontmatter import extract
from fluent_paper.references import References
from test_structure import block

class ComparisonTests(unittest.TestCase):
    def test_translation_math_and_references_are_exact(self):
        original=r'Using $x^2+\alpha$ in [-@eq-3] and [@paper-ref-1].'
        masked,values=protect(original)
        self.assertEqual(restore(masked,values),original)
        with self.assertRaises(ValueError):restore(masked.replace('ZXKEEP0XZ',''),values)
        with self.assertRaises(ValueError):restore(masked+' ZXKEEP0XZ',values)
    def test_translation_cache_tracks_text_and_model(self):
        self.assertNotEqual(fingerprint('value 1','a'),fingerprint('value 2','a'))
        self.assertNotEqual(fingerprint('value 1','a'),fingerprint('value 1','b'))
    def test_only_verified_author_and_abstract_sources(self):
        blocks=[block('a','Alice Smith and Bob Jones'),block('b','Abstract. An existing abstract.'),block('c','1 Introduction','paragraph_title')]
        response={'authors':[{'name':'Alice Smith','source_id':'a'},{'name':'Bob Jones','source_id':'a'},{'name':'Invented Person','source_id':'a'}],'abstract_ids':['b','invented']}
        with tempfile.TemporaryDirectory() as tmp,patch('fluent_paper.frontmatter.Decisions.ask',return_value=response):
            meta=extract(blocks,Path(tmp),'test')
        self.assertEqual(meta['authors'],[{'name':'Alice Smith'},{'name':'Bob Jones'}])
        self.assertEqual(meta['abstract_ids'],['b']);self.assertIn('a',meta['hidden_ids'])
    def test_figure_dot_bold_and_subfigure(self):
        b=block('f',[{'type':'image_caption','content':'Figure 3. Example'}],'image');b['sources']=[]
        refs=References([b])
        for text in ['Figure 3.','**Figure** 3.','Figure $3$.']:
            self.assertIn('[-@fig-3]',refs.convert(text))
        self.assertEqual(refs.convert('Figures 3a and 3b.'),'Figures [-@fig-3]a and [-@fig-3]b.')

    def test_translation_queue_is_idempotent_and_cache_detects_edits(self):
        import json
        from fastapi.testclient import TestClient
        from fluent_paper import cli
        from fluent_paper.server import app
        with tempfile.TemporaryDirectory() as tmp,patch.object(cli,'ROOT',Path(tmp)),patch('importlib.util.find_spec',return_value=object()):
            key='a'*24;folder=Path(tmp)/key;folder.mkdir()
            with cli.database() as db:db.execute('INSERT INTO papers VALUES (?,?,?,NULL)',(key,'Test','ready'))
            client=TestClient(app)
            for _ in range(2):self.assertEqual(client.post('/api/papers/'+key+'/translation').status_code,202)
            with cli.database() as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM translation_jobs').fetchone()[0],1)
                db.execute("UPDATE translation_jobs SET status='ready'")
            (folder/'translation-input.json').write_text(json.dumps([{'kind':'paragraph','markdown':'New text'}]))
            (folder/'translation-ja.json').write_text(json.dumps({'status':'ready','entries':{fingerprint('Old text'):{'text':'旧訳'}}}))
            self.assertEqual(client.get('/api/papers/'+key+'/translation').json()['status'],'stale')
            self.assertEqual(client.get('/api/papers/'+'b'*24+'/translation').status_code,404)

    def test_explicit_abstract_heading_overrides_missed_model_selection(self):
        blocks=[block('h','Abstract','paragraph_title'),block('a','The complete abstract.'),block('k','KEY WORDS—control'),block('i','1. Introduction','paragraph_title')]
        with tempfile.TemporaryDirectory() as tmp,patch('fluent_paper.frontmatter.Decisions.ask',return_value={'authors':[],'abstract_ids':[]}):
            meta=extract(blocks,Path(tmp),'test')
        self.assertEqual(meta['abstract_ids'],['a']);self.assertIn('h',meta['hidden_ids']);self.assertNotIn('k',meta['hidden_ids'])
