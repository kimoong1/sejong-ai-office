import hashlib
import json
from pathlib import Path

from .adapters import Context, hwpx, presentation, word, workbook
from .model import Budget, Limits, ParseError, failure
from .package import Package

MAIN_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml": "xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml": "pptx",
}


def parse_bytes(data: bytes, name: str = "document", limits: Limits | None = None):
    """Parse bytes in the current process. Use parse_file for a hard time limit."""
    limits = limits or Limits()
    if len(data) > limits.max_input_bytes:
        return failure("RESOURCE_LIMIT", "Input exceeds byte limit")
    package = None
    try:
        if not data.startswith(b"PK\x03\x04"):
            return failure("UNSUPPORTED_FORMAT", "Expected DOCX, XLSX, PPTX or HWPX ZIP package")
        digest = hashlib.sha256(data).hexdigest()
        package = Package(data, Budget(limits))
        ctx = Context(package, digest)
        if "mimetype" in package.entries and package.read("mimetype").strip() == b"application/hwp+zip":
            fmt, main = "hwpx", "Contents/content.hpf"
        else:
            types = package.xml("[Content_Types].xml")
            rels = package.relationships("")
            mains = [r["target"] for r in rels.values() if r["type"] == "officeDocument" and r["target"]]
            if len(mains) != 1:
                raise ParseError("INVALID_PACKAGE", "Exactly one internal officeDocument relationship is required")
            main = mains[0]
            content_types = {n.attr("PartName").lstrip("/"): n.attr("ContentType") for n in types.children("Override")}
            fmt = MAIN_TYPES.get(content_types.get(main, ""))
            if not fmt:
                raise ParseError("UNSUPPORTED_FORMAT", "Main content type is not a supported Office document")
        ext = Path(name).suffix.lower().lstrip(".")
        if ext and ext != fmt:
            ctx.warn("EXTENSION_MISMATCH", f"Filename extension .{ext} differs from detected {fmt}")
        if fmt == "hwpx":
            blocks = hwpx(ctx)
        else:
            blocks = {"docx": word, "xlsx": workbook, "pptx": presentation}[fmt](ctx, main)
        # Output is an extraction, never proof of complete visual interpretation.
        ctx.warn("EXTRACTION_SCOPE", "Only structured text is extracted; unvisited parts and embedded objects are not interpreted")
        result = {"ok": True, "document": {"schema_version": "1.0", "format": fmt,
            "source": {"name": Path(name).name, "sha256": digest, "bytes": len(data)},
            "blocks": blocks, "diagnostics": ctx.diagnostics,
            "capabilities": {"text": True, "source_mapping": True, "layout": False, "ocr": False, "editing": False},
            "metrics": package.budget.counts}}
        if len(json.dumps(result, ensure_ascii=False)) > limits.max_output_chars:
            raise ParseError("RESOURCE_LIMIT", "Serialized result exceeds output limit")
        return result
    except ParseError as exc:
        return failure(exc.code, str(exc), exc.part)
    except (ValueError, OverflowError, KeyError, UnicodeError) as exc:
        return failure("INVALID_PACKAGE", "Invalid package data: " + type(exc).__name__)
    finally:
        if package is not None:
            package.close()


def parse_local(path: str, limits: Limits):
    try:
        with open(path, "rb") as stream:
            data = stream.read(limits.max_input_bytes + 1)
        return parse_bytes(data, Path(path).name, limits)
    except OSError as exc:
        return failure("IO_ERROR", f"Cannot read input: {type(exc).__name__}")
