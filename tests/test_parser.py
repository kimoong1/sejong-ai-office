from dataclasses import replace
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile

from officeparse import Limits, parse_bytes, parse_file, parse_many, to_chunks, to_text
from officeparse.package import resolve_target
from officeparse.model import ParseError
from .fixtures import archive, docx, hwpx, paragraph, pptx, xlsx, relationships, W, P, A


class ParserTests(unittest.TestCase):
    def parsed(self, parts, name='sample.docx'):
        result = parse_bytes(archive(parts), name)
        self.assertTrue(result['ok'], result)
        return result['document']

    def code(self, data, code, limits=None):
        result = parse_bytes(data, limits=limits)
        self.assertFalse(result['ok'], result)
        self.assertEqual(result['error']['code'], code)
        self.assertNotIn('document', result)

    def test_word_whitespace_leading_zeros_and_headings(self):
        doc = self.parsed(docx())
        self.assertEqual(doc['blocks'][0]['level'], 1)
        self.assertEqual(doc['blocks'][1]['text'], '02139 공백 유지 ')

    def test_namespace_prefix_independent(self):
        parts = docx()
        parts['word/document.xml'] = parts['word/document.xml'].replace('w:', 'q:').replace('xmlns:w', 'xmlns:q')
        self.assertIn('02139', to_text(self.parsed(parts)))

    def test_word_current_revision_and_hidden_text(self):
        body = f'<w:del>{paragraph("삭제 비밀")}</w:del><w:ins>{paragraph("삽입")}</w:ins><w:p><w:r><w:rPr><w:vanish/></w:rPr><w:t>숨김</w:t></w:r><w:r><w:t>보임</w:t></w:r></w:p>'
        doc = self.parsed(docx(body))
        self.assertEqual(to_text(doc), '삽입\n보임')
        self.assertIn('CURRENT_REVISION', [d['code'] for d in doc['diagnostics']])

    def test_word_table_spans_and_nested_table(self):
        nested = '<w:tbl><w:tr><w:tc>' + paragraph('안쪽') + '</w:tc></w:tr></w:tbl>'
        body = '<w:tbl><w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/><w:vMerge w:val="restart"/></w:tcPr>' + paragraph('바깥') + nested + '</w:tc></w:tr></w:tbl>'
        doc = self.parsed(docx(body))
        cell = doc['blocks'][0]['children'][0]['children'][0]
        self.assertEqual(cell['column_span'], 2)
        self.assertEqual(cell['vertical_merge'], 'start')
        self.assertEqual(cell['children'][1]['type'], 'table')
        self.assertEqual(to_text(doc).count('안쪽'), 1)

    def test_word_notes(self):
        extra = {'word/_rels/document.xml.rels': relationships([('n', 'footnotes', 'footnotes.xml', '')]),
                 'word/footnotes.xml': f'<w:footnotes xmlns:w="{W}"><w:footnote w:id="-1" w:type="separator">{paragraph("제외")}</w:footnote><w:footnote w:id="1">{paragraph("각주")}</w:footnote></w:footnotes>'}
        text = to_text(self.parsed(docx(extras=extra)))
        self.assertIn('각주', text)
        self.assertNotIn('제외', text)

    def test_stable_unique_source_ids(self):
        data = archive(docx(paragraph('같음') + paragraph('같음')))
        first = parse_bytes(data)['document']
        second = parse_bytes(data)['document']
        self.assertEqual(first, second)
        a, b = first['blocks']
        self.assertNotEqual(a['id'], b['id'])
        self.assertTrue(a['source']['path'].endswith('/p[1]'))
        self.assertGreater(a['source']['line'], 0)

    def test_content_detection_and_extension_warning(self):
        doc = self.parsed(docx(), 'disguised.xlsx')
        self.assertEqual(doc['format'], 'docx')
        self.assertIn('EXTENSION_MISMATCH', [d['code'] for d in doc['diagnostics']])

    def test_xlsx_sparse_shared_formula_and_merges(self):
        doc = self.parsed(xlsx(), 'a.xlsx')
        sheet = doc['blocks'][0]
        self.assertEqual(len(sheet['children']), 2)
        self.assertEqual(sheet['children'][0]['value'], '02139')
        self.assertEqual(sheet['children'][1]['address'], 'XFD1048576')
        self.assertEqual(sheet['children'][1]['formula'], 'SUM(B1:B2)')
        self.assertEqual(sheet['children'][1]['raw'], '3')
        self.assertEqual(sheet['merged_ranges'], ['A1:B1'])

    def test_xlsx_inline_and_boolean(self):
        cells = '<c r="A1" t="inlineStr"><is><r><t>021</t></r><r><t>39 </t></r></is></c><c r="B1" t="b"><v>0</v></c>'
        values = self.parsed(xlsx(cells), 'a.xlsx')['blocks'][0]['children']
        self.assertEqual(values[0]['value'], '02139 ')
        self.assertIs(values[1]['value'], False)

    def test_xlsx_invalid_shared_index(self):
        self.code(archive(xlsx('<c r="A1" t="s"><v>99</v></c>')), 'INVALID_SHARED_STRING')

    def test_xlsx_invalid_address(self):
        self.code(archive(xlsx('<c r="XFE1"><v>7</v></c>')), 'INVALID_CELL')

    def test_xlsx_duplicate_cell(self):
        self.code(archive(xlsx('<c r="A1"/><c r="A1"/>')), 'INVALID_CELL')

    def test_pptx_uses_manifest_order_and_ignores_orphans(self):
        doc = self.parsed(pptx(), 'a.pptx')
        self.assertEqual(doc['blocks'][0]['children'][0]['text'], '첫 번째')
        self.assertEqual(doc['blocks'][1]['children'][0]['text'], '두 번째')
        self.assertNotIn('고아', to_text(doc))

    def test_pptx_alternate_branch_once(self):
        parts = pptx()
        parts['ppt/slides/slide2.xml'] = f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"><mc:AlternateContent><mc:Choice><a:p><a:r><a:t>선택</a:t></a:r></a:p></mc:Choice><mc:Fallback><a:p><a:r><a:t>대체</a:t></a:r></a:p></mc:Fallback></mc:AlternateContent></p:sld>'
        doc = self.parsed(parts, 'a.pptx')
        self.assertIn('대체', to_text(doc))
        self.assertNotIn('선택', to_text(doc))

    def test_hwpx_spine_table_and_inlined_order(self):
        doc = self.parsed(hwpx(), 'a.hwpx')
        children = doc['blocks'][0]['children']
        self.assertEqual([b['type'] for b in children], ['paragraph', 'table', 'paragraph'])
        self.assertEqual(children[0]['text'], '앞')
        self.assertEqual(children[2]['text'], '뒤')
        self.assertNotEqual(children[0]['id'], children[2]['id'])
        self.assertEqual(children[1]['children'][0]['children'][0]['column_span'], 2)
        self.assertTrue(to_text(doc).endswith('다음 절'))

    def test_chunks_bounded_and_all_references_resolve(self):
        doc = self.parsed(docx(paragraph('가' * 2500)))
        chunks = to_chunks(doc, 100)
        self.assertTrue(all(len(c['text']) <= 100 for c in chunks))
        self.assertEqual(''.join(c['text'] for c in chunks), '가' * 2500)
        self.assertEqual(chunks, to_chunks(doc, 100))
        self.assertTrue(all(c['references'][0]['block_id'] == doc['blocks'][0]['id'] for c in chunks))

    def test_chunks_invalid_limit(self):
        with self.assertRaises(ValueError):
            to_chunks(self.parsed(docx()), 0)

    def test_doctype_utf8_blocked(self):
        parts = docx()
        parts['word/document.xml'] = '<!DOCTYPE x [<!ENTITY x "secret">]>' + parts['word/document.xml']
        self.code(archive(parts), 'UNSAFE_XML')

    def test_doctype_utf16_blocked(self):
        parts = docx()
        parts['word/document.xml'] = ('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE x SYSTEM "file:///secret">' + parts['word/document.xml']).encode('utf-16')
        self.code(archive(parts), 'UNSAFE_XML')

    def test_malformed_xml_has_no_partial_content(self):
        parts = docx()
        parts['word/document.xml'] = parts['word/document.xml'][:-8]
        self.code(archive(parts), 'MALFORMED_XML')

    def test_redaction_blocks_whole_result(self):
        parts = docx(paragraph('비밀') + '<w:redact/>')
        result = parse_bytes(archive(parts))
        self.assertEqual(result['error']['code'], 'REDACTION_UNSUPPORTED')
        self.assertNotIn('비밀', json.dumps(result, ensure_ascii=False))

    def test_pptx_redaction_uri_blocks_whole_result(self):
        parts = pptx()
        parts['ppt/slides/slide1.xml'] = parts['ppt/slides/slide1.xml'].replace('</p:sld>', '<a:ext uri="{9F1B2C3D-4E5F-4A6B-8C7D-9E0F1A2B3C4D}"/></p:sld>')
        self.code(archive(parts), 'REDACTION_UNSUPPORTED')

    def test_duplicate_zip_names(self):
        stream = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(stream, 'w') as z:
                z.writestr('a.xml', 'a')
                z.writestr('a.xml', 'b')
        self.code(stream.getvalue(), 'UNSAFE_CONTAINER')

    def test_traversal_zip_entry(self):
        self.code(archive({'../secret': 'x'}), 'UNSAFE_CONTAINER')

    def test_external_slide_never_fetched(self):
        parts = pptx()
        parts['ppt/_rels/presentation.xml.rels'] = relationships([('s2', 'slide', 'https://example.invalid/x', ' TargetMode="External"')])
        self.code(archive(parts), 'MISSING_RELATIONSHIP')

    def test_relationship_escape_and_encoded_scheme(self):
        for target in ('../../secret', '%68ttps://example.invalid', '//server/share', '%ZZ'):
            with self.subTest(target=target), self.assertRaises(ParseError):
                resolve_target('word/document.xml', target)
        self.assertEqual(resolve_target('ppt/slides/slide1.xml', '..\\notesSlides\\notes1.xml'), 'ppt/notesSlides/notes1.xml')

    def test_missing_part(self):
        parts = docx()
        del parts['word/document.xml']
        self.code(archive(parts), 'MISSING_PART')

    def test_byte_budget(self):
        self.code(archive(docx()), 'RESOURCE_LIMIT', replace(Limits(), max_input_bytes=10))

    def test_entry_count_budget(self):
        self.code(archive(docx()), 'RESOURCE_LIMIT', replace(Limits(), max_entries=1))

    def test_total_inflation_budget(self):
        self.code(archive(docx()), 'RESOURCE_LIMIT', replace(Limits(), max_total_bytes=100))

    def test_encrypted_entry_rejected(self):
        data = bytearray(archive(docx()))
        for signature, flag_offset in [(b'PK\x03\x04', 6), (b'PK\x01\x02', 8)]:
            pos = data.find(signature)
            struct.pack_into('<H', data, pos + flag_offset, 1)
        self.code(bytes(data), 'ENCRYPTED')

    def test_unsupported_compression_rejected(self):
        data = bytearray(archive(docx()))
        for signature, method_offset in [(b'PK\x03\x04', 8), (b'PK\x01\x02', 10)]:
            pos = data.find(signature)
            struct.pack_into('<H', data, pos + method_offset, 12)
        self.code(bytes(data), 'UNSUPPORTED_COMPRESSION')

    def test_non_text_object_warning(self):
        doc = self.parsed(docx(paragraph('본문') + '<w:p><w:r><w:drawing/></w:r></w:p>'))
        self.assertIn('NON_TEXT_OBJECTS', [d['code'] for d in doc['diagnostics']])

    def test_pptx_notes_preserved(self):
        parts = pptx()
        parts['ppt/slides/_rels/slide2.xml.rels'] = relationships([('n', 'notesSlide', '../notesSlides/notes1.xml', '')])
        parts['ppt/notesSlides/notes1.xml'] = f'<p:notes xmlns:p="{P}" xmlns:a="{A}"><p:sp><p:nvSpPr><p:nvPr><p:ph type="body"/></p:nvPr></p:nvSpPr><p:txBody><a:p><a:r><a:t>발표자 노트</a:t></a:r></a:p></p:txBody></p:sp></p:notes>'
        doc = self.parsed(parts, 'a.pptx')
        self.assertIn('발표자 노트', to_text(doc))
        self.assertEqual(doc['blocks'][0]['children'][-1]['source']['part'], 'ppt/notesSlides/notes1.xml')

    def test_inflated_part_budget(self):
        self.code(archive(docx(paragraph('가' * 3000))), 'RESOURCE_LIMIT', replace(Limits(), max_part_bytes=2000))

    def test_node_budget(self):
        self.code(archive(docx()), 'RESOURCE_LIMIT', replace(Limits(), max_xml_nodes=2))

    def test_depth_budget(self):
        self.code(archive(docx('<w:x>' * 20 + '</w:x>' * 20)), 'RESOURCE_LIMIT', replace(Limits(), max_xml_depth=10))

    def test_text_budget(self):
        self.code(archive(docx(paragraph('a' * 100))), 'RESOURCE_LIMIT', replace(Limits(), max_text_chars=50))

    def test_block_budget(self):
        self.code(archive(docx()), 'RESOURCE_LIMIT', replace(Limits(), max_blocks=1))

    def test_output_budget(self):
        self.code(archive(docx()), 'RESOURCE_LIMIT', replace(Limits(), max_output_chars=10))

    def test_forged_underdeclared_size(self):
        data = bytearray(archive(docx(paragraph('a' * 100_000))))
        offset = 0
        while True:
            offset = data.find(b'PK\x01\x02', offset)
            if offset < 0:
                break
            nlen = struct.unpack_from('<H', data, offset + 28)[0]
            name = data[offset + 46:offset + 46 + nlen]
            if name == b'word/document.xml':
                struct.pack_into('<I', data, offset + 24, 100)
                break
            offset += 4
        self.code(bytes(data), 'CORRUPT_PART')

    def test_unknown_format(self):
        self.code(b'%PDF-1.7 not implemented', 'UNSUPPORTED_FORMAT')

    def test_bad_zip(self):
        self.code(b'PK\x03\x04junk', 'INVALID_CONTAINER')

    def test_file_worker_and_failure_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            good = Path(folder) / '한글.docx'
            good.write_bytes(archive(docx()))
            results = list(parse_many([good, Path(folder) / 'missing.docx', good], concurrency=2))
            self.assertEqual([r['ok'] for r in results], [True, False, True])
            self.assertEqual(results[1]['error']['code'], 'IO_ERROR')

    def test_hard_worker_timeout(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'a.docx'
            path.write_bytes(archive(docx()))
            self.assertEqual(parse_file(path, timeout=0.0001)['error']['code'], 'TIMEOUT')
            self.assertTrue(parse_file(path)['ok'])

    def test_invalid_configuration(self):
        for value in (0, -1, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_file('a', timeout=value)
        with self.assertRaises(ValueError):
            Limits(max_entries=0)
        with self.assertRaises(ValueError):
            list(parse_many([], concurrency=20))

    def test_cli_json_and_nonzero_for_bad_input(self):
        result = subprocess.run([sys.executable, '-m', 'officeparse', 'missing.docx'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['error']['code'], 'IO_ERROR')

    def test_cli_cannot_overwrite_input(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'a.docx'
            original = archive(docx())
            path.write_bytes(original)
            result = subprocess.run([sys.executable, '-m', 'officeparse', str(path), '--output', str(path)], capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
