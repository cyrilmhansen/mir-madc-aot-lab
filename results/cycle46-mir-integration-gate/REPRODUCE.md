# Reproduce

Compile against the verified isolated archive, not MADC's checked-out archive:

```sh
cc -std=gnu11 -O2 -Wall -Wextra -Werror -I madc/third_party/mir \
  experiments/mir-api-coverage/mir-composition.c \
  experiments/mir-api-coverage/build/mirfresh/libmir.a \
  -lm -ldl -lpthread -o experiments/mir-api-coverage/build/mir-composition
```

Run direct, serialization and optimization paths:

```sh
experiments/mir-api-coverage/build/mir-composition --opt 2
experiments/mir-api-coverage/build/mir-composition --text results/cycle46-mir-integration-gate/composite.mir --opt 2
experiments/mir-api-coverage/build/mir-composition --binary results/cycle46-mir-integration-gate/composite.bmir --opt 2
for level in 0 1 3; do experiments/mir-api-coverage/build/mir-composition --opt "$level"; done
```

Native client sources and artifact commands are in `mir-composition-aot-client.c` and `mir-composition-dlopen-client.c`. Negative probe source is `mir-validation-probe.c`. Structural injection/reduction is reproduced by building `mir-reduce-runner.c` against the same archive and running `python3 experiments/mir-api-coverage/reduce-composition.py experiments/mir-api-coverage/build/mir-reduce-runner`.

Campaign configuration, seeds/input vectors, observations, optimization matrix and artifact hashes are retained in this directory. No random generator was used; the frozen input list deterministically rebuilds the program specifications.

Emit and execute native artifacts (requires a Linux x86-64 ELF toolchain):

```sh
for level in 0 1 2 3; do
  experiments/mir-api-coverage/build/mir-composition --object "results/cycle46-mir-integration-gate/composite-o${level}.o" "$level"
  cc -std=c11 -O2 -Wall -Wextra -Werror \
    experiments/mir-api-coverage/mir-composition-aot-client.c \
    "results/cycle46-mir-integration-gate/composite-o${level}.o" \
    -o "experiments/mir-api-coverage/build/composite-aot-o${level}"
  "experiments/mir-api-coverage/build/composite-aot-o${level}"
done
clang -std=c11 -O2 -Wall -Wextra -Werror \
  experiments/mir-api-coverage/mir-composition-aot-client.c \
  results/cycle46-mir-integration-gate/composite-o2.o \
  -o experiments/mir-api-coverage/build/composite-aot-clang
experiments/mir-api-coverage/build/composite-aot-clang
experiments/mir-api-coverage/build/mir-composition --shared \
  results/cycle46-mir-integration-gate/composite.so 2
cc -std=gnu11 -O2 -Wall -Wextra -Werror \
  experiments/mir-api-coverage/mir-composition-dlopen-client.c \
  -ldl -o experiments/mir-api-coverage/build/composite-dlopen
experiments/mir-api-coverage/build/composite-dlopen \
  results/cycle46-mir-integration-gate/composite.so
```

The object and shared-library artifacts are reproducible outputs and are not committed; their original sizes and SHA-256 digests are retained in `native-artifact-inventory.json`. The source archive and public-header fingerprints used for these commands are in `provenance.json`.
