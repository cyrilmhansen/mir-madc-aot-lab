# Regression results

Executed on the current Linux x86-64 host:

- `./madc/bin/test_object_load`: 9/9 test cases, 142/142 assertions passed.
- `./madc/bin/test_native_shared`: 5/5 test cases, 169/169 assertions passed.
- `python3 -m unittest discover -s experiments/basic-workspace/tests`: 300
  tests passed in 111.847 seconds.

The latter is the direct command's reported unittest count. It is not reported
as 303 tests; prior Cycle41 campaign accounting used a different suite/counting
summary. The Workspace command emitted no failures. MIR/MADC focused tests
include some expected diagnostic text for duplicate symbols and an old object
format case, while their doctest result remains successful.

The direct Cycle42 corpus separately passed 344 interpreter/JIT cases, 344
text-round-trip cases and 344 binary-round-trip cases.
An additional `-fsanitize=undefined -fno-sanitize-recover=all` build of the
standalone harness/reference passed all 344 cases.
