"""Extraction adapters. No layout reconstruction, formula execution, or file writes."""
import hashlib
import re
from typing import Any

from .model import ParseError
from .package import Package
from .xmlsafe import Node, namespace
from .number_formats import BUILTINS, semantic_value

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WS = "http://purl.oclc.org/ooxml/wordprocessingml/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
AS = "http://purl.oclc.org/ooxml/drawingml/main"
HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
RELS = "http://purl.oclc.org/ooxml/officeDocument/relationships"


def rid(node: Node) -> str:
    return node.attrs.get(REL + "}id", node.attrs.get(RELS + "}id", ""))


def integer(value: str, default=1, maximum=16_384) -> int:
    if not re.fullmatch(r"[0-9]{1,9}", value):
        return default
    return min(max(int(value), 1), maximum)


class Context:
    def __init__(self, package: Package, digest: str):
        self.package, self.digest = package, digest
        self.diagnostics: list[dict] = []
        self._warned = set()

    def warn(self, code: str, message: str, part: str = ""):
        key = (code, part)
        if key not in self._warned:
            self._warned.add(key)
            self.diagnostics.append({"severity": "warning", "code": code, "message": message, "part": part})

    def block(self, kind: str, node: Node, part: str, **data) -> dict[str, Any]:
        self.package.budget.add("blocks", 1, self.package.budget.limits.max_blocks)
        identity = f"{self.digest}\0{part}\0{node.path}\0{kind}\0{data.get('segment', '')}"
        return {"id": hashlib.sha256(identity.encode()).hexdigest()[:24], "type": kind,
                "source": {"part": part, "path": node.path, "line": node.line}, **data}


def report_non_text(ctx: Context, root: Node, part: str):
    counts = {}
    for node in root.walk():
        if node.tag in ("pic", "chart", "equation", "oMath", "OLEObject", "oleObject", "diagram", "drawing"):
            counts[node.tag] = counts.get(node.tag, 0) + 1
    if counts:
        ctx.warn("NON_TEXT_OBJECTS", "Detected objects need separate interpretation: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())), part)


def selected_children(node: Node):
    # A single compatibility branch avoids duplicate text.
    for child in node.children():
        if child.tag == "AlternateContent":
            branch = next(iter(child.children("Fallback")), None)
            branch = branch or next(iter(child.children("Choice")), None)
            if branch:
                yield from selected_children(branch)
        else:
            yield child


def visible_text(node: Node, family: str) -> str:
    ns = {W, WS} if family == "word" else ({A, AS} if family == "drawing" else {HP})
    if node.tag == "del" and family == "word":
        return ""
    # Hidden Word runs are deliberately excluded, including complex-script text.
    if node.tag == "r" and family == "word":
        props = node.children("rPr")
        if props and any(n.tag == "vanish" and n.attr("val", "1") not in ("0", "false", "off") for n in props[0].children()):
            return ""
    if namespace(node.name) in ns:
        if node.tag == "t":
            return node.text()
        if node.tag in ("tab",):
            return "\t"
        if node.tag in ("br", "cr", "lineBreak"):
            return "\n"
    return "".join(visible_text(n, family) for n in selected_children(node))


def paragraphs(ctx: Context, root: Node, part: str, family: str) -> list[dict]:
    out = []
    for node in selected_children(root):
        if node.tag == "p" and namespace(node.name) in ({W, WS} if family == "word" else {A, AS}):
            text = visible_text(node, family)
            if not text:
                continue
            kind, extra = "paragraph", {}
            if family == "word":
                props = node.children("pPr")
                style = props[0].first("pStyle") if props else None
                outline = props[0].first("outlineLvl") if props else None
                level = re.search(r"heading([1-6])$", style.attr("val"), re.I) if style else None
                if outline and outline.attr("val").isdigit() and int(outline.attr("val")) < 6:
                    kind, extra = "heading", {"level": int(outline.attr("val")) + 1}
                elif level:
                    kind, extra = "heading", {"level": int(level.group(1))}
                elif props and props[0].first("numPr"):
                    kind = "list_item"
                if node.first("txbxContent"):
                    ctx.warn("TEXTBOX_FLATTENED", "Text boxes are flattened into their containing paragraph", part)
            out.append(ctx.block(kind, node, part, text=text, **extra))
        elif node.tag == "tbl":
            out.append(table(ctx, node, part, family))
        elif family == "word" and node.tag == "del":
            continue
        else:
            out.extend(paragraphs(ctx, node, part, family))
    return out


def table(ctx: Context, root: Node, part: str, family: str):
    rows = []
    for row_index, row in enumerate(root.children("tr")):
        cells = []
        col = 0
        for cell in row.children("tc"):
            props=cell.children('tcPr')
            props=props[0] if props else cell
            span = props.first("gridSpan") if family=='word' else None
            col_span = integer(span.attr("val")) if span else integer(cell.attr("gridSpan", "1"))
            merge = props.first("vMerge") if family=='word' else None
            merge_state = None
            if merge is not None:
                merge_state = "start" if merge.attr("val") == "restart" else "continue"
            if family == "drawing":
                merge_state = "continue" if cell.attr("vMerge") in ("1", "true") else None
            children = paragraphs(ctx, cell, part, family)
            cells.append(ctx.block("cell", cell, part, row=row_index, column=col,
                                   column_span=col_span, row_span=integer(cell.attr("rowSpan", "1")),
                                   vertical_merge=merge_state, children=children))
            col += col_span
        rows.append(ctx.block("row", row, part, index=row_index, children=cells))
    return ctx.block("table", root, part, children=rows)


def word(ctx: Context, main: str):
    root = ctx.package.xml(main)
    if root.tag != "document" or namespace(root.name) not in (W, WS):
        raise ParseError("INVALID_PACKAGE", "Main part is not a Word document", main)
    body = root.first("body")
    if body is None:
        raise ParseError("MISSING_PART", "Word document has no body", main)
    report_non_text(ctx, root, main)
    blocks = paragraphs(ctx, body, main, "word")
    if root.first("del") or root.first("ins"):
        ctx.warn("CURRENT_REVISION", "Deleted revisions omitted; inserted revisions included", main)
    relations = ctx.package.relationships(main)
    # Notes and explicitly referenced header/footer parts retain their own source.
    for rel in relations.values():
        if rel["type"] not in ("footnotes", "endnotes", "header", "footer") or not rel["target"]:
            continue
        part = rel["target"]
        extra = ctx.package.xml(part)
        if rel["type"] in ("footnotes", "endnotes"):
            content = []
            for note in extra.children():
                if note.attr("type") in ("separator", "continuationSeparator") or note.attr("id").startswith("-"):
                    continue
                content.append(ctx.block("note", note, part, number=note.attr("id"), children=paragraphs(ctx, note, part, "word")))
        else:
            content = paragraphs(ctx, extra, part, "word")
        blocks.append(ctx.block("section", extra, part, role=rel["type"], children=content))
    ctx.warn("LAYOUT_NOT_RECONSTRUCTED", "Styles, page positions, equations and drawing semantics are outside this extractor", main)
    return blocks


def presentation(ctx: Context, main: str):
    root = ctx.package.xml(main)
    if root.tag != "presentation":
        raise ParseError("INVALID_PACKAGE", "Main part is not a presentation", main)
    rels = ctx.package.relationships(main)
    out = []
    for index, item in enumerate(root.walk("sldId"), 1):
        rel = rels.get(rid(item), {})
        part = rel.get("target")
        if not part or rel.get("type") != "slide":
            raise ParseError("MISSING_RELATIONSHIP", "Slide relationship is missing or external", main)
        slide = ctx.package.xml(part)
        report_non_text(ctx, slide, part)
        children = paragraphs(ctx, slide, part, "drawing")
        pics = len(list(slide.walk("pic")))
        if pics:
            ctx.warn("IMAGES_NOT_READ", "Embedded images are not OCR processed", part)
        for nr in ctx.package.relationships(part).values():
            if nr["type"] != "notesSlide" or not nr["target"]:
                continue
            note_part = nr["target"]
            notes = ctx.package.xml(note_part)
            note_blocks = []
            for shape in notes.walk("sp"):
                ph = shape.first("ph")
                if ph is not None and ph.attr("type") in ("sldNum", "dt", "hdr", "ftr", "sldImg"):
                    continue
                note_blocks.extend(paragraphs(ctx, shape, note_part, "drawing"))
            children.append(ctx.block("section", notes, note_part, role="notes", children=note_blocks))
        if slide.first("graphicFrame"):
            ctx.warn("DRAWING_PARTIAL", "Tables are extracted; charts and SmartArt are not interpreted", part)
        out.append(ctx.block("slide", slide, part, number=index, hidden=item.attr("show") == "0" or slide.attr("show") == "0", image_count=pics, children=children))
    ctx.warn("LAYOUT_NOT_RECONSTRUCTED", "Slide text follows XML shape order, not geometric reading order", main)
    return out


def cell_address(value: str):
    match = re.fullmatch(r"([A-Za-z]{1,3})([1-9][0-9]{0,6})", value)
    if not match:
        raise ParseError("INVALID_CELL", "Invalid worksheet cell address")
    col = 0
    for char in match[1].upper():
        col = col * 26 + ord(char) - 64
    row = int(match[2])
    if col > 16_384 or row > 1_048_576:
        raise ParseError("INVALID_CELL", "Worksheet cell address is outside Excel bounds")
    return row, col


def workbook(ctx: Context, main: str):
    root = ctx.package.xml(main)
    if root.tag != "workbook":
        raise ParseError("INVALID_PACKAGE", "Main part is not a workbook", main)
    rels = ctx.package.relationships(main)
    shared = []
    styles=[]
    date1904=root.first('workbookPr')
    date1904=date1904 is not None and date1904.attr('date1904') in ('1','true')
    for rel in rels.values():
        if rel["type"] == "sharedStrings" and rel["target"]:
            strings = ctx.package.xml(rel["target"])
            shared = ["".join(t.text() for t in item.walk("t")) for item in strings.children("si")]
        elif rel['type']=='styles' and rel['target']:
            style_root=ctx.package.xml(rel['target'])
            custom={int(n.attr('numFmtId')):n.attr('formatCode') for n in style_root.walk('numFmt')}
            cell_xfs=style_root.first('cellXfs')
            if cell_xfs is not None:
                styles=[custom.get(int(n.attr('numFmtId','0')),BUILTINS.get(int(n.attr('numFmtId','0')))) for n in cell_xfs.children('xf')]
    out = []
    for item in root.walk("sheet"):
        rel = rels.get(rid(item), {})
        part = rel.get("target")
        if not part or rel.get("type") != "worksheet":
            raise ParseError("MISSING_RELATIONSHIP", "Worksheet relationship is missing or unsupported", main)
        sheet = ctx.package.xml(part)
        report_non_text(ctx, sheet, part)
        cells = []
        seen = set()
        for node in sheet.walk("c"):
            address = node.attr("r").upper()
            row, col = cell_address(address)
            if address in seen:
                raise ParseError("INVALID_CELL", "Duplicate worksheet cell", part)
            seen.add(address)
            v, f = node.first("v"), node.first("f")
            raw = v.text() if v is not None else None
            value = raw
            kind = node.attr("t", "n")
            if kind == "s":
                if raw is None or not re.fullmatch(r"[0-9]+", raw.strip()) or int(raw) >= len(shared):
                    raise ParseError("INVALID_SHARED_STRING", "Invalid shared string reference", part)
                value = shared[int(raw)]
            elif kind == "inlineStr":
                inline = node.first("is")
                value = "".join(t.text() for t in inline.walk("t")) if inline else ""
            elif kind == "b":
                if raw not in ("0", "1"):
                    raise ParseError("INVALID_CELL", "Invalid boolean cell", part)
                value = raw == "1"
            if f is not None:
                ctx.warn("FORMULA_CACHE_UNVERIFIED", "Formula cached values may be stale; formulas are never evaluated", part)
            style_index=int(node.attr('s','0'))
            code=styles[style_index] if 0<=style_index<len(styles) else None
            display=semantic_value(raw,code,date1904) if kind in ('n','') else value
            if node.attr('s') and code not in (None,'General','@') and display==raw:
                ctx.warn("NUMBER_FORMAT_PARTIAL", "Some number formats remain raw; number_format and raw value are retained", part)
            cells.append(ctx.block("cell", node, part, address=address, row=row, column=col,
                                   value=value, raw=raw, display_value=display, number_format=code, value_type=kind, style_index=node.attr("s") or None,
                                   formula=f.text() if f is not None else None,
                                   formula_attributes=dict(f.attrs) if f is not None else None))
        merges = [n.attr("ref") for n in sheet.walk("mergeCell")]
        for merge in merges:
            points = merge.split(":")
            if len(points) not in (1, 2):
                raise ParseError("INVALID_CELL", "Invalid merged-cell range", part)
            for point in points:
                cell_address(point)
        out.append(ctx.block("sheet", sheet, part, name=item.attr("name"),
                             state=item.attr("state", "visible"), merged_ranges=merges, children=cells))
    return out


def hwpx_content(ctx: Context, root: Node, part: str):
    out = []
    # Each table is a block; paragraphs around it retain their sequence.
    for child in selected_children(root):
        if child.tag == "tbl" and namespace(child.name) == HP:
            rows = []
            for ri, row in enumerate(child.children("tr")):
                cells = []
                for ci, cell in enumerate(row.children("tc")):
                    addr, span = cell.first("cellAddr"), cell.first("cellSpan")
                    cells.append(ctx.block("cell", cell, part,
                        row=int(addr.attr("rowAddr", str(ri))) if addr else ri,
                        column=int(addr.attr("colAddr", str(ci))) if addr else ci,
                        row_span=integer(span.attr("rowSpan")) if span else 1,
                        column_span=integer(span.attr("colSpan")) if span else 1,
                        children=hwpx_content(ctx, cell, part)))
                rows.append(ctx.block("row", row, part, index=ri, children=cells))
            out.append(ctx.block("table", child, part, children=rows))
        elif child.tag == "p" and namespace(child.name) == HP:
            # Flush text at each embedded table, so before/table/after stays ordered.
            pieces, segment = [], 0

            def flush():
                nonlocal segment
                if pieces:
                    segment += 1
                    out.append(ctx.block("paragraph", child, part, text="".join(pieces), segment=segment))
                    pieces.clear()

            def inline(n):
                if n.tag == "tbl" and namespace(n.name) == HP:
                    flush()
                    wrapper = Node("wrapper", {}, "", n.line, [n])
                    out.extend(hwpx_content(ctx, wrapper, part))
                elif n.tag == "t" and namespace(n.name) == HP:
                    pieces.append(n.text())
                elif n.tag in ("lineBreak", "br", "tab") and namespace(n.name) == HP:
                    pieces.append("\t" if n.tag == "tab" else "\n")
                else:
                    for x in selected_children(n):
                        inline(x)

            inline(child)
            flush()
        else:
            out.extend(hwpx_content(ctx, child, part))
    return out


def hwpx(ctx: Context):
    manifest_part = "Contents/content.hpf"
    root = ctx.package.xml(manifest_part)
    manifest = {n.attr("id"): resolve_hwpx_href(n.attr("href")) for n in root.walk("item")}
    out = []
    for index, item in enumerate(root.walk("itemref"), 1):
        part = manifest.get(item.attr("idref"))
        if not part:
            raise ParseError("MISSING_RELATIONSHIP", "HWPX spine entry is missing", manifest_part)
        if part=='Contents/header.xml':
            # Header contains document styles, not section body text. Avoid
            # constructing a second, unused style tree for every extraction.
            if part not in ctx.package.entries:
                raise ParseError('MISSING_PART','HWPX header is missing',part)
            ctx.warn('NON_SECTION_SPINE_ITEM','HWPX style header is not extracted',part)
            continue
        section = ctx.package.xml(part)
        if section.tag != "sec" or namespace(section.name) != "http://www.hancom.co.kr/hwpml/2011/section":
            ctx.warn("NON_SECTION_SPINE_ITEM", "HWPX non-section spine item is not extracted", part)
            continue
        report_non_text(ctx, section, part)
        out.append(ctx.block("section", section, part, number=index, children=hwpx_content(ctx, section, part)))
    if not out:
        raise ParseError("INVALID_PACKAGE", "HWPX has no readable spine sections", manifest_part)
    ctx.warn("LAYOUT_NOT_RECONSTRUCTED", "HWPX text/tables extracted; layout, fields and equations may be incomplete", manifest_part)
    return out


def resolve_hwpx_href(href: str) -> str:
    from .package import resolve_target
    # Hancom's HPF manifest uses package-root paths such as Contents/section0.xml.
    return resolve_target("", href)
