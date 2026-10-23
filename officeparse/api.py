import json
import math
import os
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from .model import Limits, failure


def parse_file(path, *, limits: Limits | None = None, timeout: float = 20.0):
    """Run one extraction in a disposable process; kill it after timeout seconds.

    Limits bound input/inflation/tree/output, not total OS RSS. Worker isolation
    is fault containment, not an OS security sandbox.
    """
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be positive and finite")
    limits = limits or Limits()
    env = os.environ.copy()
    root = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = root  # only this SDK must be importable in the worker
    env["PYTHONIOENCODING"] = "utf-8"
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        process = subprocess.run([sys.executable, "-m", "officeparse._worker"],
            input=json.dumps({"path": str(Path(path).resolve()), "limits": asdict(limits)}),
            text=True, encoding="utf-8", capture_output=True, timeout=timeout,
            env=env, creationflags=flags)
        if process.returncode != 0:
            return failure("WORKER_FAILED", "Parser worker exited without a result")
        if len(process.stdout) > limits.max_output_chars:
            return failure("RESOURCE_LIMIT", "Worker output exceeds limit")
        return json.loads(process.stdout)
    except subprocess.TimeoutExpired:
        return failure("TIMEOUT", f"Parsing exceeded {timeout:g} seconds")
    except (OSError, ValueError):
        return failure("WORKER_FAILED", "Cannot start worker or decode result")


def parse_many(paths, *, concurrency: int = 2, limits: Limits | None = None, timeout: float = 20.0):
    """Bounded in-flight work, input-order results, one failure per file."""
    if type(concurrency) is not int or not 1 <= concurrency <= 8:
        raise ValueError("concurrency must be an integer between 1 and 8")
    iterator = iter(paths)
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        pending = []
        for _ in range(concurrency):
            try:
                path = next(iterator)
            except StopIteration:
                break
            pending.append(executor.submit(parse_file, path, limits=limits, timeout=timeout))
        while pending:
            yield pending.pop(0).result()
            try:
                path = next(iterator)
            except StopIteration:
                continue
            pending.append(executor.submit(parse_file, path, limits=limits, timeout=timeout))
