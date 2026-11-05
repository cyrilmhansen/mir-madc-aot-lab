#!/usr/bin/env python3
"""Generate live MIR functions with a deterministic result for each entry."""
import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("count", type=int)
    parser.add_argument("output", type=Path)
    parser.add_argument("--pie-main", action="store_true",
                        help="add an entry that verifies bench_00000 and exits 0")
    args = parser.parse_args()
    if args.count <= 0:
        parser.error("count must be positive")
    lines = ["m_bench: module"]
    lines.extend(f"  export bench_{i:05d}" for i in range(args.count))
    for i in range(args.count):
        lines += [
            f"bench_{i:05d}: func i64, i64:x",
            "  local i64:r",
            f"  mul r, x, {i + 3}",
            f"  add r, r, {i * i}",
            "  ret r",
            "  endfunc",
        ]
    if args.pie_main:
        lines += [
            "  export main",
            "p_bench: proto i64, i64:x",
            "main: func i64",
            "  local i64:r",
            "  call p_bench, bench_00000, r, 17",
            "  sub r, r, 51",
            "  ret r",
            "  endfunc",
        ]
    lines.append("endmodule")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="ascii")


if __name__ == "__main__":
    main()
