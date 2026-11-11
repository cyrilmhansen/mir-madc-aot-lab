# Failure ledger

No genuine MIR execution or persistence defect was found.

1. **Initial CFG bound fixture error (harness).** First attempt admitted a value above the reference's 0..8 clamp while the MIR loop's then-current input was not equivalently bounded. The mismatch was caused by the harness generator/oracle fixture, not MIR. The failing partial rows and classification are in `failures/initial-cfg-bound-partial-output.jsonl` and `failures/initial-cfg-bound.json`. The corrected bounded corpus passes.
2. **Negative fixture accepted (expected behavior).** `ret 1` is a valid immediate return in MIR; the first negative set incorrectly expected rejection. Preserved in `negative-api-results-initial.json`. Replaced with malformed multi-value return; final 32 controls reject.
3. **Performance harness stale path.** The supplemental corpus wrote `cycle43-final.mir`, but the timing script initially referenced the earlier 256-case `cycle43-raw.mir`, which lacked new function names. This is recorded in `failures/performance-harness-stale-input.json`; script now uses the final artifact and the benchmark passes.
4. **Coverage accounting corrections.** The initial summarizer counted `local` declarations as an opcode and contained wrong static branch totals. These were corrected before final coverage output. The final script derives opcodes from MIR text and reads Cycle42 coverage names; branch totals are explicitly marked spec-derived.

Injected reducer faults are test-only and not MIR defects. See `reducer-validation.json`. No real counterexample was available to minimize.
