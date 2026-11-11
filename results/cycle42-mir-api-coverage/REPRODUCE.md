# Reproduce Cycle42

From repository root, first regenerate the API inventory and direct program:

```sh
python3 experiments/mir-api-coverage/inventory.py
mkdir -p experiments/mir-api-coverage/build results/cycle42-mir-api-coverage
cc -std=gnu11 -O2 -Wall -Wextra -I madc/third_party/mir \
  experiments/mir-api-coverage/mir-diff.c madc/obj/mir/host/libmir.a \
  -lm -ldl -lpthread -o experiments/mir-api-coverage/build/mir-diff
experiments/mir-api-coverage/build/mir-diff \
  experiments/mir-api-coverage/build/generated.mir \
  experiments/mir-api-coverage/build/generated.bmir \
  > results/cycle42-mir-api-coverage/differential-results.jsonl
experiments/mir-api-coverage/build/mir-diff --text \
  experiments/mir-api-coverage/build/generated.mir \
  > results/cycle42-mir-api-coverage/text-roundtrip.jsonl
experiments/mir-api-coverage/build/mir-diff --binary \
  experiments/mir-api-coverage/build/generated.bmir \
  > results/cycle42-mir-api-coverage/binary-roundtrip.jsonl
cmp results/cycle42-mir-api-coverage/differential-results.jsonl \
    results/cycle42-mir-api-coverage/text-roundtrip.jsonl
cmp results/cycle42-mir-api-coverage/differential-results.jsonl \
    results/cycle42-mir-api-coverage/binary-roundtrip.jsonl
```

The MADC host tests run in this environment with:

```sh
./madc/bin/test_object_load
./madc/bin/test_native_shared
python3 -m unittest discover -s experiments/basic-workspace/tests
```

The first two binaries report 9/9 cases and 142/142 assertions, and 5/5 cases
and 169/169 assertions respectively. They are MADC AOT tests, not direct
opcode coverage.
