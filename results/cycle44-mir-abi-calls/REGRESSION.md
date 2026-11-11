# Regression

| Suite | Result |
|---|---|
| Cycle42 direct MIR corpus using isolated archive | 353/353; direct/text/binary outputs byte-identical |
| Cycle43 CFG/memory corpus using isolated archive | 412/412; direct/text/binary outputs byte-identical |
| Cycle44 interpreter/JIT/text/binary | 52 signatures × 5 seeds per route; zero mismatches |
| MADC object-load | 9 cases, 142 assertions passed |
| MADC native-shared | 5 cases, 169 assertions passed |
| BASIC Workspace pytest | 303 tests, 148 subtests passed |

The MADC test binary prints one compatibility notice for a legacy test object predating its current init-array model; the suite exits successfully. Historical raw results were not rewritten.
