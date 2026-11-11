# Metrics

| Metric | Result |
|---|---:|
| New production MIR/MADC changes | 0 |
| New direct MIR semantic cases | 353 |
| Directly constructed MIR functions | 345 |
| Concrete opcodes in Cycle42 direct corpus | 30 |
| Pinned concrete instruction denominator | 248 |
| MIR type values enumerated | 18 |
| Types exercised by this corpus | 2 (I64, D) |
| Independent oracle comparisons | 353 per execution path |
| Fresh MIR text parse/JIT cases | 353 |
| Fresh MIR binary decode/JIT cases | 353 |
| Interpreter/JIT/text/binary mismatches | 0 |
| UBSan harness/reference findings | 0 |
| New reducer-confirmed discrepancies | 0 |

There are no gateway, transaction or Workspace production changes. The
experiment tooling is a C harness and a Python inventory generator; generated
executables and `.mir`/`.bmir` inputs are reproducible build artifacts excluded
from version control.
