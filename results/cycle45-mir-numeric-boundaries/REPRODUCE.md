# Reproduce

From repository root, build against the isolated archive (do not replace MADC's checkout archive):

```sh
cc -std=gnu11 -O2 -Wall -Wextra -Werror -I madc/third_party/mir \
  experiments/mir-api-coverage/mir-numeric-corpus.c \
  experiments/mir-api-coverage/build/mirfresh/libmir.a \
  -lm -ldl -lpthread -o experiments/mir-api-coverage/build/mir-numeric-corpus
experiments/mir-api-coverage/build/mir-numeric-corpus
experiments/mir-api-coverage/build/mir-numeric-corpus --text results/cycle45-mir-numeric-boundaries/program.mir
experiments/mir-api-coverage/build/mir-numeric-corpus --binary results/cycle45-mir-numeric-boundaries/program.bmir
```

The reducer runner is built similarly from `mir-reduce-runner.c`; then run `python3 experiments/mir-api-coverage/reduce-numeric.py experiments/mir-api-coverage/build/mir-reduce-runner`. Native object client commands are included in the campaign record and generated source.

Selected AOT fixture:

```sh
experiments/mir-api-coverage/build/mir-numeric-corpus --object results/cycle45-mir-numeric-boundaries/numeric.o
cc -std=c11 -O2 -Wall -Wextra -Werror experiments/mir-api-coverage/mir-numeric-aot-client.c results/cycle45-mir-numeric-boundaries/numeric.o -o experiments/mir-api-coverage/build/cycle45-native-client
experiments/mir-api-coverage/build/cycle45-native-client
```

The committed evidence keeps the client source and output, not the generated object or executable. The negative-control ledger is explicitly scanner-level syntax classification and must not be read as a semantic type-check result.
