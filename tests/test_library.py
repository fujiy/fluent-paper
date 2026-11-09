import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fluent_paper import cli

class LibraryTests(unittest.TestCase):
    def test_duplicate_content_has_one_job(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(cli, 'ROOT', Path(tmp) / 'private'):
            pdf = Path(tmp) / 'a.pdf'
            pdf.write_bytes(b'%PDF-1.7\nfixture')
            first = cli.add(pdf)
            renamed = Path(tmp) / 'b.pdf'
            renamed.write_bytes(pdf.read_bytes())
            self.assertEqual(first, cli.add(renamed))
            with cli.database() as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM papers').fetchone()[0], 1)
            self.assertEqual((cli.ROOT / first / 'source.pdf').read_bytes(), pdf.read_bytes())

    def test_invalid_input_does_not_enter_queue(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(cli, 'ROOT', Path(tmp) / 'private'):
            path = Path(tmp) / 'bad.pdf'; path.write_text('not a PDF')
            with self.assertRaises(ValueError): cli.add(path)
            self.assertFalse(cli.ROOT.exists())

if __name__ == '__main__': unittest.main()
