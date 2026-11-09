import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from fluent_paper import cli
from fluent_paper.server import app
from fluent_paper.correction import validate
from fluent_paper.reader import safe_markdown

class PipelineTests(unittest.TestCase):
    def test_math_characters_preserved(self):
        text=r'$$A &= B < C \\ D > E$$'
        self.assertEqual(safe_markdown(text),text)
    def test_scripts_removed(self):
        self.assertNotIn('<script',safe_markdown('<script>alert(1)</script>hello'))
    def test_executable_cells_disabled(self):
        self.assertNotIn('```{',safe_markdown('```{python}\nprint(1)\n```'))
    def test_model_cannot_change_number(self):
        self.assertFalse(validate('value is 10','value is 100'))
    def test_model_cannot_remove_negation(self):
        self.assertFalse(validate('is not stable','is stable'))
    def test_model_spacing_only(self):
        self.assertTrue(validate('the  value is 10','the value is 10'))
    def test_api_upload_and_deduplication(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(cli,'ROOT',Path(tmp)):
            client=TestClient(app)
            for _ in range(2):
                response=client.post('/api/papers',files={'file':('p.pdf',b'%PDF-1.7\nfixture','application/pdf')},headers={'accept':'application/json'})
                self.assertEqual(response.status_code,202)
            self.assertEqual(len(client.get('/api/papers').json()),1)
    def test_cross_site_upload_rejected(self):
        response=TestClient(app).post('/api/papers',headers={'origin':'https://evil.invalid'})
        self.assertEqual(response.status_code,403)
    def test_bad_host_rejected(self):
        self.assertEqual(TestClient(app).get('/',headers={'host':'evil.invalid'}).status_code,400)
    def test_traversal_rejected(self):
        self.assertEqual(TestClient(app).get('/papers/'+'a'*24+'/%2e%2e/%2e%2e/library.sqlite').status_code,404)
    def test_zip_traversal_rejected(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp,patch.object(cli,'ROOT',Path(tmp)):
            folder=Path(tmp)/('a'*24)/'parsed';folder.mkdir(parents=True)
            with zipfile.ZipFile(folder/'source.zip','w') as z:z.writestr('../escape.txt','bad')
            with self.assertRaises(ValueError):cli.build('a'*24,'title')
            self.assertFalse((folder.parent/'escape.txt').exists())

if __name__=='__main__':unittest.main()
