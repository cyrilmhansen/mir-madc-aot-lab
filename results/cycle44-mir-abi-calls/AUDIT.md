# Audit

The public API census in `mir-api-inventory.json` extends Cycle43's header/archive inventory. Cycle44 directly used function/prototype array constructors, call/return construction, imports/exports, external binding, interpreter arrays, link/JIT, text and binary persistence, native object/shared emission and object loading.

The variadic counterparts `MIR_new_func`, `MIR_new_proto` and `MIR_new_call_insn` were inspected but not used; their `_arr` equivalents avoid C varargs ambiguities in a generated typed corpus. `MIR_new_jcall_insn` was inspected but not used for ordinary C ABI coverage for the non-standard ABI reason below. Declarations and symbol-export status are present in the inherited 181-entry census.

The declared APIs `MIR_new_jcall_insn` and `MIR_new_jret_insn` are present but were not exercised as C ABI calls: the pinned `MIR.md` documents `MIR_JCALL/JRET` as a non-standard ABI intended to transfer control without ordinary call/return setup. Ordinary external calls used `MIR_CALL` with a matching `MIR_proto`.

The initial MADC archive SHA-256 was recorded, but its build inputs/flags cannot be reconstructed from the archive alone. A fresh archive was built from the unchanged checked-out source in `experiments/mir-api-coverage/build/mirfresh`; both archive hashes and the exact build flags are in `provenance.json`. The source subtree matches the historical MADC pin; the full MADC checkout is at the Cycle43-observed commit. Neither checkout nor archive was changed.

An initial diagnostic during harness development was first suspected to indicate header/archive opcode disagreement. Inspection of the generated MIR showed the harness emitted `MOV` for a double source. The isolated rebuild reproduced the same diagnostic, and correcting the fixture fixed it. The conclusion was withdrawn: no archive/header mismatch was established.
