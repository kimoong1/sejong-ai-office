"""Ordered, namespace-aware XML tree with cumulative limits and DTD rejection."""
from dataclasses import dataclass, field
from xml.parsers import expat

from .model import Budget, ParseError


def local(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def namespace(name: str) -> str:
    return name.rsplit("}", 1)[0] if "}" in name else ""


@dataclass
class Node:
    name: str
    attrs: dict[str, str]
    path: str
    line: int
    content: list = field(default_factory=list)

    @property
    def tag(self) -> str:
        return local(self.name)

    def attr(self, name: str, default: str = "") -> str:
        # Unqualified attributes win; namespace-qualified lookups can be exact.
        if name in self.attrs:
            return self.attrs[name]
        return next((v for k, v in self.attrs.items() if local(k) == name), default)

    def children(self, tag: str | None = None):
        return [n for n in self.content if isinstance(n, Node) and (tag is None or n.tag == tag)]

    def walk(self, tag: str | None = None):
        if tag is None or self.tag == tag:
            yield self
        for child in self.children():
            yield from child.walk(tag)

    def text(self) -> str:
        return "".join(n if isinstance(n, str) else n.text() for n in self.content)

    def first(self, tag: str):
        return next(self.walk(tag), None)


def parse_xml(chunks, budget: Budget, part: str) -> Node:
    parser = expat.ParserCreate(namespace_separator="}")
    stack: list[Node] = []
    counts: list[dict[str, int]] = [{}]
    root = None

    def reject(*_):
        raise ParseError("UNSAFE_XML", "DTD and entity declarations are forbidden", part)

    def start(name, attrs):
        nonlocal root
        budget.add("xml_nodes", 1, budget.limits.max_xml_nodes)
        if len(stack) >= budget.limits.max_xml_depth:
            raise ParseError("RESOURCE_LIMIT", "XML nesting exceeds limit", part)
        # This SDK cannot enforce IeumOffice's withheld-run semantics yet.
        # Fail the entire extraction before returning any text, including notes.
        marker = "{9F1B2C3D-4E5F-4A6B-8C7D-9E0F1A2B3C4D}"
        if "redact" in local(name).lower() or any(
            "redact" in local(k).lower() or marker.casefold() == v.casefold()
            for k, v in attrs.items()
        ):
            raise ParseError("REDACTION_UNSUPPORTED", "Withholding mark requires the original redaction pipeline", part)
        tag = local(name)
        siblings = counts[-1]
        siblings[tag] = siblings.get(tag, 0) + 1
        path = (stack[-1].path if stack else "") + f"/{tag}[{siblings[tag]}]"
        node = Node(name, attrs, path, parser.CurrentLineNumber)
        if stack:
            stack[-1].content.append(node)
        else:
            root = node
        stack.append(node)
        counts.append({})

    def text(value):
        budget.add("xml_text_chars", len(value), budget.limits.max_text_chars)
        if stack:
            stack[-1].content.append(value)

    parser.StartElementHandler = start
    parser.EndElementHandler = lambda _: (stack.pop(), counts.pop())
    parser.CharacterDataHandler = text
    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.ExternalEntityRefHandler = reject
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    try:
        for chunk in chunks:
            parser.Parse(chunk, False)
        parser.Parse(b"", True)
    except expat.ExpatError as exc:
        raise ParseError("MALFORMED_XML", f"Invalid XML at line {exc.lineno}, column {exc.offset}", part) from exc
    if root is None:
        raise ParseError("MALFORMED_XML", "XML has no document element", part)
    return root
