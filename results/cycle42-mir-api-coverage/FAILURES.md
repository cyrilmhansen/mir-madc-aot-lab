# Failures and limitations

No semantic mismatch occurred in the final 353-case direct corpus or its text
and binary round trips. A minimized compile-only reproducer found that direct
inclusion of `mir.h` fails strict ISO C11 because the public
`MIR_interp_arr_varg` declaration uses `va_list` without including
`<stdarg.h>`. Preincluding that standard header makes the same source compile.
This is an API header self-containment issue, not a runtime or JIT defect; the
pinned files were left unchanged. The reproducer is
`counterexamples/header-standalone.c`, with compiler output in
`header-probe.json`.

One initial harness run triggered SIGFPE because the first operand table
supplied zero divisors to DIV/MOD. This was a generator defect, not a MIR
finding; the fixture now replaces zero divisors with one and the final run
passes.

No MIR semantic/runtime product defect was discovered. The header issue has a
minimal reproducer; no production correction was made. The current campaign
did not implement a minimized malformed-input corpus or systematically test
aborting API errors.
The current campaign did not implement a minimized malformed-input corpus or
systematically test aborting API errors. Existing API-error and object-loader
observations remain separately documented in historical lab evidence.

The principal coverage limitation is that this campaign directly tests only
30 of 248 concrete opcodes, using I64 and D, plus one bounded loop. Broader
control flow, memory, vectors, multi-return, varargs, and the full object-loader relocation
surface still require direct generated fixtures.
