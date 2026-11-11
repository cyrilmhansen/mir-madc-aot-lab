# Generator

`mir-numeric-corpus.c` builds a deterministic typed set directly with MIR APIs. It has no random generator: fixed boundary arrays and operation tables are the frozen source of all cases. The confirmatory corpus has 14 × 17 conversion observations and eight × 13 overflow pairs, with overflow flag and result checked independently. The reducer uses a smaller typed-spec subset and regenerates MIR text for every candidate before a fresh process runs interpreter and JIT.
