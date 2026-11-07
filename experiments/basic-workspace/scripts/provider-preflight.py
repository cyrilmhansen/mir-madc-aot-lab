#!/usr/bin/env python3
"""Validate the configured model listing and bounded tool-calling endpoint."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiment.provider_config import (ProviderConfigError, resolve_config,
                                        run_preflight)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--probe-timeout", type=float, default=45.0)
    parser.add_argument("--output", type=Path, help="Optional sanitized JSON result path")
    args = parser.parse_args()
    try:
        config = resolve_config(args.config) if args.config else resolve_config()
        result = run_preflight(config, args.probe_timeout)
    except ProviderConfigError as exc:
        result = {"schema": "basic-workspace.provider-preflight", "version": 1,
                  "status": "configuration_error", "message": str(exc)}
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
