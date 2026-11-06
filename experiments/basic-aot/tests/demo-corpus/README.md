# AWARI generated MIR failure reproductions

`awari-adapter-crash.mir` is the exact 56,090-byte MIR text emitted for the
historical AWARI demo by the experimental BASIC frontend. `unmatched-for-goto.bas`
is the four-line reduction of its control-flow shape: a second `FOR` branches
back to a `NEXT` that lexically closes the first `FOR`. The generated MIR has a
branch to an undefined loop exit label. `undefined-label-minimal.mir` is the
smallest standalone MIR case found for the downstream crash.

Run `experiments/basic-aot/scripts/repro-awari-adapter-crash.sh` from the lab
to regenerate and check all three failure paths. The expected result is an
adapter SIGSEGV. This is a bug in BASIC's MIR generation for this unusual loop
control flow; the minimal MIR also shows that the adapter/MIR reader-link path
fails to diagnose an undefined branch target cleanly.

Captured traces:

- `awari-gdb.txt`: AWARI backtrace, failing C expression, and faulting x86-64
  load (`op->u.label->data`, `cmpq $0,(%rsi)`, RSI=0).
- `awari-minimal-gdb.txt`: reduced MIR backtrace in `skip_labels` during
  `MIR_link` simplification.
- `awari-asan.txt`: fully instrumented MIR ASan/UBSan stack, showing the
  uninitialized `0xbebebebe...` next link at `mir.c:4410`.
