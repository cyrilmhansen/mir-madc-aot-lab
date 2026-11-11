# Cycle46: Compositional correctness and backend readiness gate

## Result

The frozen corpus contains **24 composite specifications** across six families, represented by 32 MIR functions including helpers. The 160 independent observations passed through the MIR interpreter and JIT. Fresh text parse, fresh binary decode, and a second fresh process produced byte-identical result records. All observations also matched the independent C reference.

The tested compositions carry meaningful values across mechanisms: narrowing controls branches; overflow state selects branches and is passed to a helper; narrow memory values are converted, arithmetically transformed and stored; loops load and extend array bytes; and mixed integer/double callers convert a value, call an internal helper, then consume caller-live state.

Optimization levels 0, 1, 2 and 3 all matched on the 160 observations. ET_REL objects emitted at each level passed 16 independent GCC client checks; level 2 also passed 16 Clang checks. The level-2 shared object passed eight `dlopen`/`dlsym` calls. Two injected composite discrepancies were structurally reduced while preserving their branch or memory boundary.

No valid-program MIR defect was observed. One malformed branch-label input reliably caused SIGSEGV in MIR linking; it is recorded as an invalid-input diagnostic/validation risk, not a valid-code correctness failure.

## Coverage and limits

Six of the eight proposed composition families ran. The confirmation set did not include cross-module composition, a MIR-imported external C helper, `MIR_object_load`, PIE, or an independently generated second input configuration. These remain untested by Cycle46 itself; relevant Cycle44 results are not counted as composite coverage. Performance samples are process-level and exploratory.

## Regression

Cycle42 (353), Cycle43 (412), Cycle44 (52 signature shapes), Cycle45 (446), MADC object-load (9 cases/142 assertions), MADC native-shared (5/169), and Workspace pytest (303 tests/148 subtests) passed. The MADC checkout remained untouched. See `REGRESSION.md`.

## Readiness and recommendation

The evidence supports a scoped backend integration prototype for the tested Linux x86-64 MIR subset. It does not establish all-opcode or cross-target correctness. The concrete invalid-label crash means an integrating frontend must validate MIR control-flow targets before linking.

**Decision: close the broad direct-MIR validation phase and move to a real compiler adapter prototype.** A PL/I-80 adapter first needs a source-language lowering and ABI inventory; no `drpli` port is implied. The decision rationale and checklist are in `EXIT-DECISION.md`, with the detailed capability matrix in `BACKEND-READINESS.md`.
