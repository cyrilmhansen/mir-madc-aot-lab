# Regression

Cycle40 baseline: 295 tests and 134 subtests. Cycle41 adds focused contract, table, equivalence, mismatch, row-order, handle-resolution and continuation-binding tests. The focused Cycle41 suite passed **8 tests and 14 subtests**. The complete Workspace suite passed **303 tests and 148 subtests** in 121.24 seconds. The suite was rerun after the final test changes; historical raw evidence remains unchanged.

Command:

```sh
python -m pytest -q experiments/basic-workspace/tests
```

Covered historical paths include Cycle19 construction, Cycle20 v1/v2 maintenance, Cycle26/Cycle37 rename, Cycle31 portable replay, Cycle34 cross-function edits, Cycle35 creation sequences, Cycle36 handoff, Cycle38 continuation, and Cycle39/Cycle40 generated and production tests.
