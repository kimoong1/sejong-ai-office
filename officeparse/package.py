import io
import posixpath
import re
import zipfile
import zlib
from urllib.parse import unquote, urlsplit

from .model import Budget, ParseError
from .xmlsafe import parse_xml


def resolve_target(base: str, target: str) -> str:
    try:
        target = unquote(target.strip(), errors="strict").replace("\\", "/")
    except (UnicodeError, ValueError) as exc:
        raise ParseError("UNSAFE_RELATIONSHIP", "Invalid relationship encoding", base) from exc
    if re.search(r"%(?![0-9a-fA-F]{2})", target):
        raise ParseError("UNSAFE_RELATIONSHIP", "Invalid relationship escape", base)
    url = urlsplit(target)
    if not target or url.scheme or url.netloc or url.query or url.fragment or "\x00" in target:
        raise ParseError("UNSAFE_RELATIONSHIP", "Relationship is not an internal package path", base)
    stack = [] if target.startswith("/") else [x for x in posixpath.dirname(base).split("/") if x]
    for segment in target.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if not stack:
                raise ParseError("UNSAFE_RELATIONSHIP", "Relationship escapes package root", base)
            stack.pop()
        else:
            stack.append(segment)
    return "/".join(stack)


class Package:
    def __init__(self, data: bytes, budget: Budget):
        self.budget = budget
        try:
            self.zip = zipfile.ZipFile(io.BytesIO(data))
        except (zipfile.BadZipFile, OSError) as exc:
            raise ParseError("INVALID_CONTAINER", "Not a readable ZIP package") from exc
        self.entries = {}
        try:
            infos = self.zip.infolist()
            if len(infos) > budget.limits.max_entries:
                raise ParseError("RESOURCE_LIMIT", "ZIP entry count exceeds limit")
            declared_total = 0
            for entry in infos:
                name = entry.filename
                if name.startswith(("/", "\\")) or "\\" in name or any(x in (".", "..") for x in name.split("/")) or ":" in name or "\x00" in name:
                    raise ParseError("UNSAFE_CONTAINER", "Unsafe ZIP entry name")
                if name in self.entries:
                    raise ParseError("UNSAFE_CONTAINER", "Duplicate ZIP entry", name)
                if entry.flag_bits & 1:
                    raise ParseError("ENCRYPTED", "Encrypted ZIP entries are unsupported", name)
                if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise ParseError("UNSUPPORTED_COMPRESSION", "Only stored and deflated entries are accepted", name)
                if entry.file_size > budget.limits.max_part_bytes:
                    raise ParseError("RESOURCE_LIMIT", "ZIP part exceeds byte limit", name)
                declared_total += entry.file_size
                if declared_total > budget.limits.max_total_bytes:
                    raise ParseError("RESOURCE_LIMIT", "ZIP declared total exceeds byte limit")
                self.entries[name] = entry
        except Exception:
            self.zip.close()
            raise

    def close(self):
        self.zip.close()

    def chunks(self, part: str):
        if part not in self.entries:
            raise ParseError("MISSING_PART", "Required package part is missing", part)
        count = 0
        try:
            with self.zip.open(self.entries[part]) as stream:
                while chunk := stream.read(32 * 1024):
                    count += len(chunk)
                    if count > self.budget.limits.max_part_bytes:
                        raise ParseError("RESOURCE_LIMIT", "Inflated part exceeds byte limit", part)
                    self.budget.add("inflated_bytes", len(chunk), self.budget.limits.max_total_bytes)
                    yield chunk
        except (zipfile.BadZipFile, OSError, EOFError, RuntimeError, zlib.error) as exc:
            raise ParseError("CORRUPT_PART", "Package part failed decompression or CRC validation", part) from exc
        if count != self.entries[part].file_size:
            raise ParseError("CORRUPT_PART", "Inflated size differs from ZIP declaration", part)

    def xml(self, part: str):
        return parse_xml(self.chunks(part), self.budget, part)

    def read(self, part: str) -> bytes:
        return b"".join(self.chunks(part))

    def relationships(self, base: str):
        path = posixpath.join(posixpath.dirname(base), "_rels", posixpath.basename(base) + ".rels") if base else "_rels/.rels"
        if path not in self.entries:
            return {}
        root = self.xml(path)
        if root.tag != "Relationships":
            raise ParseError("INVALID_PACKAGE", "Invalid relationships root", path)
        result = {}
        for rel in root.children("Relationship"):
            key, mode = rel.attr("Id"), rel.attr("TargetMode")
            if not key or key in result:
                raise ParseError("INVALID_PACKAGE", "Missing or duplicate relationship id", path)
            if mode and mode != "External":
                raise ParseError("INVALID_PACKAGE", "Unknown relationship target mode", path)
            result[key] = {"type": rel.attr("Type").rsplit("/", 1)[-1], "target": None if mode == "External" else resolve_target(base, rel.attr("Target"))}
        return result
