import unittest
from officeparse import parse_bytes, to_text
from officeparse.number_formats import semantic_value
from .fixtures import archive, docx, xlsx, relationships


class ImprovementTests(unittest.TestCase):
    def test_web_hidden_is_print_visible(self):
        parts=docx('<w:p><w:r><w:t>TOC entry</w:t></w:r><w:r><w:rPr><w:webHidden/></w:rPr><w:t>7</w:t></w:r></w:p>')
        result=parse_bytes(archive(parts))
        self.assertEqual(to_text(result['document']),'TOC entry7')

    def test_date_systems_leap_and_rollover(self):
        self.assertEqual(semantic_value('44155','yyyy-mm-dd'),'2020-11-20')
        self.assertEqual(semantic_value('0','yyyy-mm-dd',True),'1904-01-01')
        self.assertEqual(semantic_value('60','yyyy-mm-dd'),'1900-02-29')
        self.assertEqual(semantic_value('1','yyyy-mm-dd'),'1900-01-01')
        self.assertEqual(semantic_value('1.5','yyyy-mm-dd hh:mm:ss'),'1900-01-01 12:00:00')

    def test_number_formats_preserve_raw_semantics(self):
        self.assertEqual(semantic_value('2139','00000'),'02139')
        self.assertEqual(semantic_value('0.125','0.0%'),'12.5%')
        self.assertEqual(semantic_value('1.5','[h]:mm:ss'),'36:00:00')
        self.assertEqual(semantic_value('12345678901234567890','General'),'12345678901234567890')

    def test_date_cell_has_both_raw_and_display(self):
        parts=xlsx('<c r="A1" s="1"><v>44155</v></c>')
        parts['xl/_rels/workbook.xml.rels']=relationships([('sheet','worksheet','worksheets/sheet3.xml',''),('styles','styles','styles.xml','')])
        parts['xl/styles.xml']='<styleSheet><cellXfs><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>'
        result=parse_bytes(archive(parts))
        cell=result['document']['blocks'][0]['children'][0]
        self.assertEqual(cell['raw'],'44155')
        self.assertEqual(cell['value'],'44155')
        self.assertEqual(cell['display_value'],'2020-11-20')
        self.assertIn('2020-11-20',to_text(result['document']))
