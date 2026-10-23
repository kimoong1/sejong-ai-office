import argparse
import json
import math
from pathlib import Path
import sys

from .api import parse_many
from .export import to_chunks, to_text


def main():
    parser = argparse.ArgumentParser(description="Structured DOCX/XLSX/PPTX/HWPX extraction")
    parser.add_argument("files", nargs="+")
    parser.add_argument("--format", choices=("json", "text", "chunks"), default="json")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--output", type=Path, help="Optional output file; multiple inputs become JSONL")
    args = parser.parse_args()
    if not 1 <= args.concurrency <= 8:
        parser.error('--concurrency must be between 1 and 8')
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('--timeout must be positive and finite')
    if args.output:
        target = args.output.resolve()
        for source in map(Path, args.files):
            same_file = source.exists() and target.exists() and source.samefile(target)
            if source.resolve() == target or same_file:
                parser.error('--output must differ from every input file')
    stream = args.output.open("w", encoding="utf-8") if args.output else sys.stdout
    failed = False
    try:
        for result in parse_many(args.files, concurrency=args.concurrency, timeout=args.timeout):
            failed |= not result["ok"]
            if result["ok"] and args.format == "text":
                stream.write(to_text(result["document"]) + "\n")
            else:
                if result["ok"] and args.format == "chunks":
                    result = {"ok": True, "source": result["document"]["source"], "chunks": to_chunks(result["document"]),
                              "diagnostics": result["document"]["diagnostics"]}
                stream.write(json.dumps(result, ensure_ascii=False) + "\n")
    finally:
        if args.output:
            stream.close()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
