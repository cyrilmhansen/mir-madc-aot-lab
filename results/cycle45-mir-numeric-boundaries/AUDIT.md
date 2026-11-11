# Audit

The root remained at `a2be66e0ab1522a7f052bdb802e4f18fbc6011b4` during the initial audit. MADC remained at `868847a76434058483bade03ead09ba6acb9d771`; its MIR subtree matched the historical pin. No MADC files were changed.

The isolated archive used for Cycle45 is `experiments/mir-api-coverage/build/mirfresh/libmir.a`, SHA-256 `9ee503c7bedf7f490df5e097441474b9977cf5fd1c0b497f2297a926528a594a`. The checked-out archive has a different hash, `a1e6f02f014b11796dadcc3628e369a3c0bb0039c604b6fe8b36c8a081f52bb8`. The former was rebuilt separately from the current MIR subtree; this does not establish that it is byte-identical to the historic upstream build.

`MIR_LD_IS_D=1` on this host. Thus LD types and opcodes canonicalize to D; they do not form an independent long-double precision family here.
