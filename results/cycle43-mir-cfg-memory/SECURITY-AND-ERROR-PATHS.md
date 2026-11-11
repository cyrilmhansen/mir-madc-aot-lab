# Error-path and safety results

`negative-api-results.json` contains 32 isolated MIR text-scan cases. All 32 were rejected (no timeouts), covering unknown opcodes, wrong arity, undeclared registers, invalid output lvalues, return-signature mismatch and malformed syntax. They execute in a child process; this is parser/API robustness evidence, not a semantic oracle campaign.

The initial `ret 1` case was accepted because immediate returns are legal; that generator classification error is preserved separately. Experiments also observed that text scanning alone accepts some unresolved-label and invalid-scale constructs. Those were not executed: validation is deferred and running potentially invalid control flow/memory would not be a safe valid-corpus test. Invalid memory addresses, unsupported operand scales and malformed binary execution were not fuzzed.

Two injected expectation mismatches were minimized by selecting smaller already-executed valid inputs. The reducer preserves its test-only mismatch class but does not reduce the MIR program structure. No assertion/crash is classified as a product bug here.
