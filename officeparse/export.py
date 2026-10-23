"""Deterministic text and RAG chunks with block-level evidence."""
import hashlib


def units(block):
    kind = block["type"]
    if "text" in block:
        prefix = "#" * block.get("level", 1) + " " if kind == "heading" else ("- " if kind == "list_item" else "")
        yield prefix + block["text"], block
    elif kind == "cell" and "address" in block:
        value = block.get("display_value", block["value"])
        value = ("TRUE" if value else "FALSE") if isinstance(value, bool) else str(value) if value is not None else ""
        formula = block.get("formula")
        if formula is not None:
            value += f" [formula: ={formula}; cache unverified]"
        yield f"{block['address']}: {value}", block
    elif kind == "cell" and "children" in block:
        values = [text for child in block["children"] for text, _ in units(child)]
        label = f"[row={block['row']} col={block['column']} span={block.get('row_span', 1)}x{block.get('column_span', 1)}] "
        yield label + " / ".join(values), block
    else:
        label = None
        if kind == "sheet":
            label = f"# Sheet: {block['name']}"
        elif kind == "slide":
            label = f"# Slide {block['number']}"
        elif kind == "section" and "role" in block:
            label = f"## {block['role']}"
        if label:
            yield label, block
        for child in block.get("children", []):
            yield from units(child)


def to_text(document):
    return "\n".join(text for block in document["blocks"] for text, _ in units(block))


def to_chunks(document, max_chars: int = 1200):
    """No duplicate overlap; long units split with offsets in the rendered unit."""
    if type(max_chars) is not int or max_chars < 32:
        raise ValueError("max_chars must be an integer of at least 32")
    chunks, texts, refs, size = [], [], [], 0

    def flush():
        nonlocal texts, refs, size
        if not texts:
            return
        text = "\n".join(texts)
        identity = document["source"]["sha256"] + repr(refs) + text
        chunks.append({"id": hashlib.sha256(identity.encode()).hexdigest()[:24], "text": text, "references": refs})
        texts, refs, size = [], [], 0

    for block in document["blocks"]:
        for text, source in units(block):
            for start in range(0, len(text), max_chars):
                piece = text[start:start + max_chars]
                addition = len(piece) + bool(texts)
                if size + addition > max_chars:
                    flush()
                    addition = len(piece)
                texts.append(piece)
                refs.append({"block_id": source["id"], "source": source["source"],
                             "rendered_start": start, "rendered_end": start + len(piece)})
                size += addition
    flush()
    return chunks
