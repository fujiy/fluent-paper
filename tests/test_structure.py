import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fluent_paper.structure import restore, text
from fluent_paper.references import References


def block(id, value, kind='text', page=1, bbox=None):
    return {'id':id,'type':kind,'page':page,'bbox':bbox or [.1,.2,.45,.8],
            'original':{'type':kind,'content':value},'corrections':[]}


class StructureTests(unittest.TestCase):
    def restore(self, blocks, decision=None):
        with tempfile.TemporaryDirectory() as tmp:
            if decision:
                with patch('fluent_paper.structure.Decisions.ask',side_effect=decision):
                    return restore({'blocks':blocks},Path(tmp),'test')
            return restore({'blocks':blocks},Path(tmp),'')

    def test_page_split_joins_before_figure_placement(self):
        a=block('a','See Fig. 1 for the')
        f=block('f',[{'type':'image_caption','content':'Figure 1. Model'}],'image')
        b=block('b','model used here.',page=2)
        r=self.restore([a,f,b])
        self.assertEqual([x['id'] for x in r['blocks']],['a','f'])
        self.assertEqual(text(r['blocks'][0]['original']),'See Fig. 1 for the model used here.')
        self.assertEqual([s['id'] for s in r['blocks'][0]['sources']],['a','b'])
        self.assertEqual(r['blocks'][1]['scope_ids'],['a'])

    def test_complete_paragraph_and_equation_are_boundaries(self):
        r=self.restore([block('a','Complete.'),block('b','another paragraph',page=2),block('e',r'x=1','equation',2),block('c','continued',page=3)])
        self.assertEqual(r['aliases'],{})

    def test_numbered_hierarchy(self):
        r=self.restore([block('a','3 Method','paragraph_title'),block('b','3.1 Model','paragraph_title'),block('c','3.1.1 Detail','paragraph_title')])
        self.assertEqual([b['level'] for b in r['blocks']],[2,3,4])

    def test_scope_cannot_escape_candidate_neighborhood(self):
        blocks=[block('a','Background.'),block('b','Fig. 1 shows the result.'),block('c','This explains the curve.'),block('d','Unrelated later work.'),block('f',[{'type':'image_caption','content':'Figure 1. Result'}],'image')]
        r=self.restore(blocks,lambda *args:{'paragraph_ids':['b','c','d','invented'],'reason':'test'})
        self.assertEqual(r['blocks'][-1]['id'],'d')
        self.assertEqual(next(b for b in r['blocks'] if b['id']=='f')['scope_ids'],['b','c'])

    def test_native_reference_syntax_preserves_math(self):
        blocks=[block('e',r'x=1\tag{33}','equation'),block('f',[{'type':'image_caption','content':'Figure 2. Model'}],'image'),block('r','[7] Smith, J. (2020). A study.','ref_text')]
        for b in blocks:b['sources']=[]
        refs=References(blocks)
        self.assertEqual(refs.convert(r'Fig. 2, Eq. (33), [7]; $x=(33)$'),r'Fig. [-@fig-2], Eq. ([-@eq-33]), [@paper-ref-1]; $x=(33)$')

    def test_superscript_citation_is_not_a_power(self):
        b=block('r','1) Smith, J. (2020). Study.','ref_text');b['sources']=[]
        refs=References([b])
        self.assertEqual(refs.convert(r'Result $^{1)}$ but $x^{1}$ and $10^{1}$.'),r'Result [@paper-ref-1] but $x^{1}$ and $10^{1}$.')

    def test_japanese_and_grouped_figure_references(self):
        blocks=[block('a','Figs. 1 and 2 show results. 第2図 also shows them.'),block('f',[{'type':'image_caption','content':'第2図 結果'}],'image')]
        r=self.restore(blocks)
        figure=next(b for b in r['blocks'] if b['id']=='f')
        self.assertEqual(figure['label'],('fig','2'))
        self.assertEqual(figure['scope_ids'],['a'])
        refs=References(r['blocks'])
        self.assertEqual(refs.convert('第2図'), '第[-@fig-2]図')

    def test_unknown_superscript_is_preserved(self):
        refs=References([])
        self.assertEqual(refs.convert(r'Unknown $^{99)}$.'),r'Unknown $^{99)}$.')
