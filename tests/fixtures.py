import io
import zipfile
from xml.sax.saxutils import escape

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
HP = 'http://www.hancom.co.kr/hwpml/2011/paragraph'
HS = 'http://www.hancom.co.kr/hwpml/2011/section'
CT = {
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml',
}
MAIN = {'docx': 'word/document.xml', 'xlsx': 'xl/workbook.xml', 'pptx': 'ppt/presentation.xml'}


def archive(parts):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    return stream.getvalue()


def relationships(items):
    return '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(
        f'<Relationship Id="{key}" Type="{R}/{kind}" Target="{target}"{extra}/>'
        for key, kind, target, extra in items) + '</Relationships>'


def office(fmt, xml, extras=None):
    main = MAIN[fmt]
    return {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        f'<Override PartName="/{main}" ContentType="{CT[fmt]}"/></Types>',
        '_rels/.rels': relationships([('main', 'officeDocument', main, '')]),
        main: xml, **(extras or {}),
    }


def paragraph(text, props=''):
    return f'<w:p>{props}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def docx(body=None, extras=None):
    body = body if body is not None else paragraph('2026년 사업 계획', '<w:pPr><w:pStyle w:val="Heading1"/></w:pPr>') + paragraph('02139 공백 유지 ')
    return office('docx', f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>', extras)


def xlsx(cells=None):
    cells = cells if cells is not None else '<c r="A1" t="s"><v>0</v></c><c r="XFD1048576"><f>SUM(B1:B2)</f><v>3</v></c>'
    return office('xlsx', f'<workbook xmlns="{S}" xmlns:r="{R}"><sheets><sheet name="예산" sheetId="1" r:id="sheet"/></sheets></workbook>', {
        'xl/_rels/workbook.xml.rels': relationships([('sheet', 'worksheet', 'worksheets/sheet3.xml', ''), ('ss', 'sharedStrings', 'sharedStrings.xml', '')]),
        'xl/sharedStrings.xml': f'<sst xmlns="{S}"><si><r><t>02</t></r><r><t>139</t></r></si></sst>',
        'xl/worksheets/sheet3.xml': f'<worksheet xmlns="{S}"><sheetData><row r="1">{cells}</row></sheetData><mergeCells><mergeCell ref="A1:B1"/></mergeCells></worksheet>',
    })


def slide(text):
    return f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>'


def pptx():
    return office('pptx', f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst><p:sldId id="1" r:id="s2"/><p:sldId id="2" r:id="s1"/></p:sldIdLst></p:presentation>', {
        'ppt/_rels/presentation.xml.rels': relationships([('s1', 'slide', 'slides/slide1.xml', ''), ('s2', 'slide', 'slides/slide2.xml', '')]),
        'ppt/slides/slide1.xml': slide('두 번째'), 'ppt/slides/slide2.xml': slide('첫 번째'),
        'ppt/slides/slide99.xml': slide('고아 슬라이드'),
    })


def hwpx():
    cell = '<hp:tc><hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="2" rowSpan="1"/><hp:subList><hp:p><hp:run><hp:t>셀</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
    return {'mimetype': 'application/hwp+zip',
        'Contents/content.hpf': '<package><manifest><item id="s1" href="Contents/section1.xml"/><item id="s0" href="Contents/section0.xml"/></manifest><spine><itemref idref="s1"/><itemref idref="s0"/></spine></package>',
        'Contents/section1.xml': f'<hs:sec xmlns:hs="{HS}" xmlns:hp="{HP}"><hp:p><hp:run><hp:t>앞</hp:t><hp:tbl><hp:tr>{cell}</hp:tr></hp:tbl><hp:t>뒤</hp:t></hp:run></hp:p></hs:sec>',
        'Contents/section0.xml': f'<hs:sec xmlns:hs="{HS}" xmlns:hp="{HP}"><hp:p><hp:run><hp:t>다음 절</hp:t></hp:run></hp:p></hs:sec>'}
