# Reproduce Cycle44

From repository root, regenerate signatures and clients, build an isolated MIR archive in the ignored experiment build tree, then compile the harness:

```sh
python3 experiments/mir-api-coverage/cycle44-abi-matrix.py
mkdir -p experiments/mir-api-coverage/build/mirfresh
make -C madc/third_party/mir \
  SRC_DIR="$PWD/madc/third_party/mir" \
  BUILD_DIR="$PWD/experiments/mir-api-coverage/build/mirfresh" \
  "$PWD/experiments/mir-api-coverage/build/mirfresh/libmir.a" -j2
cc -std=gnu11 -O2 -Wall -Wextra -Werror \
  -I madc/third_party/mir -I experiments/mir-api-coverage/build \
  experiments/mir-api-coverage/mir-abi-corpus.c \
  experiments/mir-api-coverage/build/mirfresh/libmir.a \
  -lm -ldl -lpthread -o experiments/mir-api-coverage/build/mir-abi-corpus-fresh
```

Then run direct, text, binary, object, shared and loader paths:

```sh
experiments/mir-api-coverage/build/mir-abi-corpus-fresh --run > results/cycle44-mir-abi-calls/direct-run.jsonl 2> results/cycle44-mir-abi-calls/direct-run.stderr
experiments/mir-api-coverage/build/mir-abi-corpus-fresh --generate results/cycle44-mir-abi-calls/program.mir results/cycle44-mir-abi-calls/program.bmir
experiments/mir-api-coverage/build/mir-abi-corpus-fresh --text results/cycle44-mir-abi-calls/program.mir > results/cycle44-mir-abi-calls/text-run.jsonl 2> results/cycle44-mir-abi-calls/text-run.stderr
experiments/mir-api-coverage/build/mir-abi-corpus-fresh --binary results/cycle44-mir-abi-calls/program.bmir > results/cycle44-mir-abi-calls/binary-run.jsonl 2> results/cycle44-mir-abi-calls/binary-run.stderr
experiments/mir-api-coverage/build/mir-abi-corpus-fresh --object results/cycle44-mir-abi-calls/mir-abi.o
cc -std=gnu11 -O2 -Wall -Wextra -Werror -rdynamic experiments/mir-api-coverage/build/cycle44-native-client.c results/cycle44-mir-abi-calls/mir-abi.o -ldl -o experiments/mir-api-coverage/build/cycle44-native-client
experiments/mir-api-coverage/build/cycle44-native-client
experiments/mir-api-coverage/build/mir-abi-corpus-fresh --shared results/cycle44-mir-abi-calls/libmir-abi.so
cc -std=gnu11 -O2 -Wall -Wextra -Werror -rdynamic experiments/mir-api-coverage/build/cycle44-native-client.c -L results/cycle44-mir-abi-calls -l:libmir-abi.so -Wl,-rpath,"$PWD/results/cycle44-mir-abi-calls" -ldl -o experiments/mir-api-coverage/build/cycle44-shared-client
experiments/mir-api-coverage/build/cycle44-shared-client results/cycle44-mir-abi-calls/libmir-abi.so
experiments/mir-api-coverage/build/mir-abi-corpus-fresh --load-object results/cycle44-mir-abi-calls/mir-abi.o
experiments/mir-api-coverage/build/mir-abi-corpus-fresh --load-object-missing-import results/cycle44-mir-abi-calls/mir-abi.o
```

The last command is expected to reject with an unresolved-symbol diagnostic. `cycle44-inventory.py` and `cycle44-performance.py` regenerate provenance/census and the registered process-level measurements. `generated-signatures.json` marks the first 48 shapes confirmatory and the last four exploratory. The object, shared library and binary MIR files are generated artifacts and are not required to be committed.
