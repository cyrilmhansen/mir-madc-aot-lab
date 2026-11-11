# Optimization comparison

Levels 0, 1, 2 and 3 were executed in fresh processes on all 160 observations. Their JSONL outputs were byte-identical. Each of four optimization levels also emitted an ELF object; an independent GCC C client executed 16 selected composite calls from each object (64 total) without mismatch. At level 2, an independent Clang client also passed 16 checks. A level-2 shared library passed eight `dlopen`/`dlsym` calls. No semantic optimization sensitivity was observed in this bounded set.

Level 0 is MIR's fast generation tier, not a claim of conventional compiler `-O0` semantics. Levels are implementation settings, not promised user-facing optimization grades. Object size and per-level timings are recorded in the artifact and performance ledgers where collected.
