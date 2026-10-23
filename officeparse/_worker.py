import json
import sys

from .core import parse_local
from .model import Limits, failure


def main():
    try:
        request = json.load(sys.stdin)
        result = parse_local(request["path"], Limits(**request["limits"]))
    except MemoryError:
        result = failure("RESOURCE_LIMIT", "Worker ran out of memory")
    except Exception:
        result = failure("WORKER_FAILED", "Unexpected parser failure")
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
