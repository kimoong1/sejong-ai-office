from dataclasses import asdict, dataclass
from typing import Any


class ParseError(Exception):
    def __init__(self, code: str, message: str, part: str | None = None):
        super().__init__(message)
        self.code, self.part = code, part


@dataclass(frozen=True)
class Limits:
    max_input_bytes: int = 50 * 1024 * 1024
    max_entries: int = 4096
    max_part_bytes: int = 16 * 1024 * 1024
    max_total_bytes: int = 128 * 1024 * 1024
    max_xml_nodes: int = 300_000
    max_xml_depth: int = 96
    max_text_chars: int = 4_000_000
    max_blocks: int = 100_000
    max_output_chars: int = 24_000_000

    def __post_init__(self):
        for key, value in asdict(self).items():
            if type(value) is not int or value < 1:
                raise ValueError(f"{key} must be a positive integer")


class Budget:
    def __init__(self, limits: Limits):
        self.limits = limits
        self.counts: dict[str, int] = {}

    def add(self, key: str, amount: int, maximum: int):
        self.counts[key] = self.counts.get(key, 0) + amount
        if self.counts[key] > maximum:
            raise ParseError("RESOURCE_LIMIT", f"{key} exceeds configured limit")


def failure(code: str, message: str, part: str | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if part:
        error["part"] = part
    return {"ok": False, "error": error}
