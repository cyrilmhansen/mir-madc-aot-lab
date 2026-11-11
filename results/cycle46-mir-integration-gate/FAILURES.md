# Failures

No valid composite program disagreed with its independent oracle across interpreter, JIT, text, binary, optimization or selected native paths. Two expected-value mistakes in the initial C native client and one reducer setup-order defect were corrected; details are preserved in `harness-defects.json`.

A focused invalid-input probe with a missing branch label was accepted by text scanning and module load, then crashed with SIGSEGV during `MIR_link` in `build_func_cfg` (`mir-gen.c:2476`, dereferencing `op->u.label->data`). The exact program, repeated crash and GDB backtrace are preserved in `invalid_branch_label.mir`, `negative-results.json`, `invalid-branch-repeat.*` and `invalid-branch-gdb.txt`. This is malformed MIR, not a valid-program semantic failure; the public API's promised behavior for this malformed input was not established. It is reported as an error-diagnostic/validation risk, not as a confirmed valid-code backend defect. No upstream sources were modified.
