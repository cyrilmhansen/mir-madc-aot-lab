# Oracle

The oracle is independent C code in `mir-numeric-corpus.c`. It does not call MIR, parse projections or consume backend outputs. Narrow conversions use masks and explicit sign extension; 64-bit bit patterns are reinterpreted with `memcpy`; overflow predicates use wide mathematical intermediates. Float-to-integer values are finite and in-range, so C truncation toward zero is defined. Floating conversion observations use exact host bit patterns.

This corpus establishes agreement on its finite inputs only. It does not prove behavior for NaN, infinities, subnormals, alternate rounding modes, out-of-range float-to-integer conversions, or every possible integer value.
