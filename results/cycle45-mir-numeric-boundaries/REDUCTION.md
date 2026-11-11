# Structural reduction

`reduce-numeric.py` deletes typed operations together with dependent operations, regenerates valid MIR text, and invokes `mir-reduce-runner.c` in a fresh process after each accepted step. It preserves the required opcode, failure class, JIT observation boundary and independent expected output.

Two test-only comparator faults were reduced: conversion fixture 4 operations → 1 (`ext8`, input 128), and overflow fixture 3 unrelated setup operations → 0 while retaining `addo` plus the overflow branch. These are harness injections, not MIR defects. Full original and reduced specifications, MIR text and step logs are stored in the result directory.
