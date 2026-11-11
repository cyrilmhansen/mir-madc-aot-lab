# Control-flow coverage

124 cases exercise 10 MIR functions across nine families: conditional diamond, three-way decision, bounded counter loop, bounded accumulation loop, nested conditions, nested two-loop accumulation, multiple early returns, signed/unsigned comparison distinction, and equivalent CFG arrangements.

The functions contain 4–8 basic blocks by the label/terminator leader count. Conditional inputs cover both outcomes for every recorded `BLT`, `BGE`, `BGT`, `BEQ`, and `UBLT` site. The corpus has forward jumps and loop backedges; loop bounds are at most 8 per dimension (nested loop body at most 64 iterations for the input bounds). Programs initialize locals before use and terminate within the fixed limit.

Both equivalent CFG functions match the independent clamp-like reference. The signed/unsigned fixture uses negative and nonnegative I64 values around the high-bit boundary; it confirms distinct outcomes for signed and unsigned ordering. No indirect branch, `SWITCH`, overflow branch, or floating branch was executed.

Basic-block counts and specified branch outcome totals are machine-readable in `cfg-coverage.json`. Outcomes are inferred from the frozen mathematical cases, not collected through runtime branch instrumentation.
