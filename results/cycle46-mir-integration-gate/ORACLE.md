# Oracle

The composite harness computes expected results in C from hand-defined formulas. Conversion-plus-branch uses explicit low-byte sign/zero interpretation. Overflow uses `__int128`/`__uint128_t` bounds. Memory cases use initialized byte arrays, explicit signed-byte interpretation, bounded indices and independent expected stores. Mixed-call cases use finite exactly representable/truncation inputs within I64 range. Checksums are kept in bounded ranges.

Hand checks include EXT8(128) = -128; UEXT8(255) = 255; INT64_MAX + 1 sets signed overflow and wraps to INT64_MIN; byte 0x80 sign-extends to -128 before adding one; and D2I(-3.75) truncates to -3. Oracle facts are recorded independently of MIR outputs.
