# Generator and frozen campaign

The direct generator is the C fixture builder in `experiments/mir-api-coverage/mir-cfg-memory.c`; the standalone C reference functions are adjacent but separate from MIR execution. Case ordering and values are fixed tables, not random samples. The initial campaign config was frozen before execution. After auditing actual typed memory/address coverage, a supplemental finite memory set was preregistered before that supplemental run to cover signed/unsigned 16- and 32-bit forms and additional indexed 16-bit forms.

Final corpus: 124 CFG + 288 memory = 412 cases; 10 CFG functions and 24 memory functions. Input ranges are fixed in source. Every CFG input is deterministic, loop dimensions are bounded by 8; memory cases use twelve fixed scalar values and four bounded index positions. No generator accepts arbitrary MIR or unsafe pointer values.

`generated-cases.jsonl` contains exact case inputs and expected/observed values. `generated-programs.mir` and `.bmir` preserve the pre-link module. A second deterministic execution is stored in `confirmation-run.jsonl`.
