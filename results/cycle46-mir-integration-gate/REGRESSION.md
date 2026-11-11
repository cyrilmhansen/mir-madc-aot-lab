# Regression

| Suite | Result |
|---|---|
| Cycle42 direct MIR | 353 cases passed |
| Cycle43 CFG/memory | 412 cases passed |
| Cycle44 ABI | 52 signature shapes × 5 inputs; zero mismatches |
| Cycle45 numerical | 446 observations passed |
| Cycle46 composites | 160 observations; interpreter/JIT/text/binary/repeat agreement |
| MADC object-load | 9 cases, 142 assertions passed |
| MADC native-shared | 5 cases, 169 assertions passed |
| BASIC Workspace | 303 tests, 148 subtests passed |

The Cycle42–45 executable regression clients were built for the Cycle44 isolated archive, whose fingerprint was reverified as `9ee503c7bedf7f490df5e097441474b9977cf5fd1c0b497f2297a926528a594a`. Cycle46 direct/composite binaries were compiled against that same archive. The MADC checkout stayed at `868847a76434058483bade03ead09ba6acb9d771`; no source or archive in the submodule was modified.
