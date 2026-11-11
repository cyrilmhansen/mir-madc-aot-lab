# Reproduce Cycle43

From the repository root, build the direct harness against the existing archive:

```sh
cc -std=gnu11 -O2 -Wall -Wextra -Werror -I madc/third_party/mir \
  experiments/mir-api-coverage/mir-cfg-memory.c madc/obj/mir/host/libmir.a \
  -lm -ldl -lpthread -o experiments/mir-api-coverage/build/mir-cfg-memory
experiments/mir-api-coverage/build/mir-cfg-memory \
  experiments/mir-api-coverage/build/cycle43-final.mir \
  experiments/mir-api-coverage/build/cycle43-final.bmir \
  > results/cycle43-mir-cfg-memory/differential-results.jsonl
experiments/mir-api-coverage/build/mir-cfg-memory --text \
  experiments/mir-api-coverage/build/cycle43-final.mir \
  > results/cycle43-mir-cfg-memory/text-roundtrip.jsonl
experiments/mir-api-coverage/build/mir-cfg-memory --binary \
  experiments/mir-api-coverage/build/cycle43-final.bmir \
  > results/cycle43-mir-cfg-memory/binary-roundtrip.jsonl
cmp results/cycle43-mir-cfg-memory/differential-results.jsonl \
    results/cycle43-mir-cfg-memory/text-roundtrip.jsonl
cmp results/cycle43-mir-cfg-memory/differential-results.jsonl \
    results/cycle43-mir-cfg-memory/binary-roundtrip.jsonl
```

The generated inputs are preserved in this directory. `cycle43-performance.py` runs the preregistered two warmups + seven measurements per route. `cycle43-coverage.py` rebuilds the machine-readable coverage summaries. `invalid-cases.py` uses the compiled isolated parser probe.

Additional regressions:

```sh
./madc/bin/test_object_load
./madc/bin/test_native_shared
python3 -m pytest -q experiments/basic-workspace/tests
```

The native object check can be repeated with `--emit-object`, then compile `mir-aot-client.c` against the emitted object. Build and archive assumptions are documented in `AUDIT.md`.
