# Independent reference semantics

The C reference function in `mir-diff.c` is independent of MIR execution and
uses only the input integers and declared operation. The generated arithmetic
cases avoid signed overflow for addition and subtraction. Multiplication
expectations use defined `uint64_t` modulo arithmetic, including wraparound;
signed division/remainder avoid zero and INT64_MIN / -1.
Bitwise operations use `uint64_t`. Shifts use valid counts; left and logical
right shifts are over unsigned values. Arithmetic right shift is explicitly
sign-filled instead of relying on implementation-defined C behavior.
`EXT8` sign-extends the low byte, and `UEXT8` zero-extends it.

This finite corpus checks exact 64-bit result bit patterns. It does not cover
floating-point rounding, NaNs, infinities, signed zero, narrow MIR type
promotion, vector lanes, overflow-setting instructions, or memory semantics.


The 56 floating cases use finite `MIR_T_D` values for which the selected
operations and comparisons have exactly representable results (halves,
integers, and exact quotients). The independent C double calculation is
compared exactly for this selected corpus. No general ULP tolerance is used;
non-exact rounding and exceptional IEEE cases are not included.
