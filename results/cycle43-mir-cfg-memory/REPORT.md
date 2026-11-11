# Cycle43 — Control-flow and memory differential falsification

## Result

The bounded direct-MIR corpus completed with 412 valid cases: 124 control-flow cases over 10 functions and 288 memory cases over 24 functions. Direct MIR construction was compared against independent C reference behavior, then run through the MIR interpreter, MIR JIT, fresh text parse and fresh binary decode. The four result streams are byte-identical. A second fresh direct run is also identical. GCC, Clang and UBSan builds agree.

The memory campaign covers 25 distinct typed operation/address tuples, including I8/U8/I16/U16/I32/U32/I64 loads and stores, indexed offsets, aliasing, and bounded indexed updates. Eight-byte canaries and the entire 80-byte allocation are checked. I16 scale-1 indexed loads exercise unaligned in-bounds addresses using a `memcpy` C reference.

Selected native object emission and linkage through a separate C client passed for `cfg_diamond` and `mem_store_reload64`. The client verified returns and surrounding bytes. This does not establish general ABI or object-loader correctness.

No MIR execution defect was found. One initial CFG mismatch was caused by the test oracle using a bound of 8 while the first generated input still exceeded it; that attempt and correction are retained. One negative fixture used `ret 1`, which MIR accepts as a legal immediate return; it was replaced with an invalid multi-value return. A benchmark script initially referenced the preserved 256-case input instead of the expanded artifact; the path error is recorded and the benchmark rerun passed.

## Qualification

The available archive is `libmir.a` SHA-256 `a1e6f02f014b11796dadcc3628e369a3c0bb0039c604b6fe8b36c8a081f52bb8`. Its exact build provenance is not established. The checked-out MADC commit is `868847a76434058483bade03ead09ba6acb9d771`, not the historical f541 pin. The MIR source subtree is byte-identical at the recorded tree hash; neither MADC nor MIR was modified or rebuilt.

The strict-C11 `mir.h` self-containment problem was reproduced with GCC and Clang. Preincluding `<stdarg.h>` makes both compile. No upstream issue was opened and no source was changed.

## Acceptance levels

- Level 0: pass with qualification; current host APIs are usable, archive provenance remains unverified.
- Level 1: pass; direct programmatic CFG and memory test constructors and independent references are reproducible.
- Level 2: pass; interpreter, JIT, text and binary observations agree on 412 cases.
- Level 3: pass; nine CFG families, both observed outcomes for conditional branches, forward/backward edges and bounded loops.
- Level 4: pass; memory loads/stores, 8/16/32/64-bit widths, signedness, indexed scales, aliasing and canaries checked.
- Level 5: partial; 32 isolated malformed-input probes classified, but deferred label/scale validation and unsafe execution boundaries were not probed.
- Level 6: partial; two injected expectation mismatches were reduced over already executed inputs, but the reducer does not rewrite CFGs or memory operation sequences.
- Level 7: partial; two selected native object functions passed independent C-client linkage. `MIR_object_load`, shared library, PIE and cross-target paths were not exercised here.
- Level 8: pass; 34/248 cumulative enumerated opcode names were covered across Cycles42–43; Cycle43 adds four unique opcodes. Memory addressing is reported separately.
- Level 9: exploratory pass; repeated same-host end-to-end measurements completed. Internal phase timing was not instrumented.
- Level 10: no genuine MIR defect found.

The campaign is bounded and does not prove MIR correct outside the tested programs, inputs and host. See the audit, coverage files and reproduction instructions.
