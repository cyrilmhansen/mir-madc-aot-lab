#!/usr/bin/env python3
"""Small deterministic smoke-fuzz for malformed worker transport inputs."""
from __future__ import annotations

import json
from pathlib import Path
import random
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "native/build/mir-worker"


def main() -> None:
    if not WORKER.is_file():
        raise SystemExit("build the worker first with scripts/build-mir-worker.sh")
    rng = random.Random(7)
    for index in range(100):
        payload = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 128)))
        result = subprocess.run([str(WORKER)], input=payload, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=2, check=False)
        if result.returncode != 0:
            raise SystemExit(f"payload {index} exited {result.returncode}: {result.stderr!r}")
        try:
            response = json.loads(result.stdout)
        except Exception as error:
            raise SystemExit(f"payload {index} returned non-JSON output: {result.stdout!r}") from error
        if response.get("ok") is not False:
            raise SystemExit(f"payload {index} was not rejected: {response!r}")
    print("100 seeded malformed payloads returned structured errors")


if __name__ == "__main__":
    main()
