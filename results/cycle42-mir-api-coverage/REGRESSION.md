# Regression results

Executed on the current Linux x86-64 host:

- `./madc/bin/test_object_load`: 9/9 test cases, 142/142 assertions passed.
- `./madc/bin/test_native_shared`: 5/5 test cases, 169/169 assertions passed.
- `python3 -m unittest discover -s experiments/basic-workspace/tests`: 300
  tests passed in 111.847 seconds.
- `python3 -m pytest -q experiments/basic-workspace/tests`: 303 passed, 148
  subtests passed in 121.75 seconds, matching the Cycle41 baseline.

The unittest command reports test methods; pytest is the baseline-comparable
case count. Both commands completed without failures. MIR/MADC focused tests
include some expected diagnostic text for duplicate symbols and an old object
format case, while their doctest result remains successful.

The direct Cycle42 corpus separately passed 353 interpreter/JIT cases, 353
text-round-trip cases and 353 binary-round-trip cases.
An additional `-fsanitize=undefined -fno-sanitize-recover=all` build of the
standalone harness/reference passed all 353 cases.
