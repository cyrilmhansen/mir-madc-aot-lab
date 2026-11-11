# Architecture

The C harness constructs conversion and overflow functions through the public MIR API, independently calculates expected values, then executes interpreter and JIT paths. It writes MIR text and binary formats; fresh invocations parse/decode and rerun the same specification. A second small public-API client executes a serialized MIR program generated from a bounded typed reducer specification. No BASIC Workspace, MADC C frontend, new MIR feature, or production runtime modification is used.

The numerical oracle uses explicit bit reinterpretation, narrow-width masking/sign extension, finite in-range float-to-integer inputs, and `__int128`/`__uint128_t` intermediates for overflow predicates. MIR 32-bit overflow arithmetic compares only low 32 result bits because the high result bits are documented as undefined.
