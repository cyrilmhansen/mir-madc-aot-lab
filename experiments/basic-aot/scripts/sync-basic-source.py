#!/usr/bin/env python3
"""Copy the pristine extracted BASIC subtree into the ignored MIR build tree."""
import pathlib
import shutil
import sys

source, destination = map(pathlib.Path, sys.argv[1:3])
for src in source.rglob("*"):
    if not src.is_file():
        continue
    dst = destination / src.relative_to(source)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists() or src.read_bytes() != dst.read_bytes():
        shutil.copy2(src, dst)
