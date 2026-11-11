# Cycle45 report

## Result

The bounded direct MIR campaign executed 14 conversion opcodes and eight overflow opcodes against an independently calculated reference. All 446 interpreter observations agreed with the JIT and reference; fresh text and binary parses agreed across the same corpus. A MIR-generated ELF relocatable object linked to an independent C client and passed 12 selected conversion/overflow checks.

The structural reducer removed irrelevant MIR operations from two injected failures while retaining valid typed programs and the original observation boundary. No genuine MIR defect was found.

## Limits

Long double is canonicalized to double on this build (`MIR_LD_IS_D=1`). Nonfinite and out-of-range float-to-integer values were excluded. This campaign does not cover conversion chains, converted branch conditions, AOT coverage for all opcodes, or separate unsigned overflow branches for ADDO/SUBO. Performance evidence is exploratory only.

## Regression

MADC object-load passed (9 cases / 142 assertions), native-shared passed (5 / 169), Cycle42/43/44 corpora passed, and BASIC Workspace pytest passed (303 tests, 148 subtests). See `REGRESSION.md`.

See `AUDIT.md`, `OPCODE-CONTRACTS.md`, `CONVERSION-COVERAGE.md`, `OVERFLOW-COVERAGE.md`, `REDUCTION.md` and `REPRODUCE.md`.

## Acceptance levels

| Level | Status | Evidence / limit |
|---|---|---|
| 0 Contract audit | Partial | Audited tested forms; LD canonicalizes to D. |
| 1 Valid numerical corpus | Pass | 14 conversions, eight overflow opcodes, fixed boundary inputs. |
| 2 Differential correctness | Pass | Interpreter/JIT/text/binary exact agreement for 446 observations. |
| 3 Conversion coverage | Partial | Signedness, narrowing, widening and rounding; no explicit conversion chains. |
| 4 Overflow coverage | Pass with limit | Result and signed/unsigned multiply flags; ADDO/SUBO unsigned-flag branch not separately observed. |
| 5 Combined semantics | Partial | Overflow-to-branch composed; converted-value conditional branches not included. |
| 6 Native execution | Pass | 12 distinct exported function checks via independent C client. |
| 7 Structural reduction | Pass | Both injected mismatches reduced structurally and replayed in fresh processes. |
| 8 Error classification | Partial | 25 isolated MIR text scanner controls; 19 rejected, six accepted by syntax scanner. This is not a full semantic type-check campaign. |
| 9 Coverage growth | Pass | 18 new opcode names; cumulative 56/248. |
| 10 Regression | Pass | Cycle42–44 harnesses, two MADC suites and Workspace pytest passed. |
| 11 Genuine defect discovery | No finding | No confirmed MIR defect observed. |

A second randomized seed was not run. The corpus is fixed and deterministic; a fresh-process repetition would test reproducibility but would not represent new seed diversity. The result is therefore not claimed at that target.
