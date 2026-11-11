# Direct MIR API campaign

This test-only harness constructs MIR functions through `mir.h`, links only
against the checked-out `libmir.a`, and checks interpreter/JIT results against
an independent C calculation. It does not invoke the MADC frontend.

Run from the repository root:

```sh
python3 experiments/mir-api-coverage/inventory.py
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
```

`build/` contains reproducible generated MIR artifacts and the executable; it
is excluded from version control. The checked-in JSONL outputs contain each
input and result for comparison.
