# Generator

`experiments/mir-api-coverage/cycle44-abi-matrix.py` deterministically constructs the 48 preregistered ordered signatures and emits a C include with exact-prototype wrappers, typed argument arrays and C reference functions. Four post-freeze exploratory shapes exercise mixed GP/SSE stack spills and are marked `exploratory` in the machine-readable signatures. The generated native client contains both static-prototype ELF callers and typed `dlsym` callers.

The direct MIR constructor is `experiments/mir-api-coverage/mir-abi-corpus.c`. It uses only public MIR constructors and records API execution modes. Seeds 0–4 are the confirmatory input set; object/native clients use deterministic values and three repeated calls. The case list is reproducible by rerunning the generator; no random state is implicit.
