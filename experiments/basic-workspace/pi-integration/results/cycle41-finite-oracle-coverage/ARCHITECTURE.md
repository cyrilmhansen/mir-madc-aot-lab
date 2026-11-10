# Architecture

Cycle20 v3 adds one host data representation at the existing validation boundary. `_expected_observations()` maps positional table rows into the same `{engine: {input: {result_key: value}}}` shape used by v1/v2. Candidate preview and `validate_current()` still call the shared MIR execution loop and compare the same normalized observation map. Target authorization, structural candidate checks, dependency and identity checks, `SemanticTransactionKernel`, canonical Workspace operations, TypeScript tools and portable replay are unchanged.

The contract table supplies expectations; it does not authorize any operation. The host owns the specification and table. Cycle20 authorizes only its exact existing `per_target` target set and permitted replacements. MIR interpreter and JIT execute the candidate independently against those host expectations. The continuation verifier binds the complete v3 destination-contract artifact to the external trust anchor before the receiver starts.

Version compatibility is explicit: v1 remains single-function scope; v2 remains per-target with the original formula oracle declarations; v3 is per-target with `finite_expected_results`. No oracle expression interpreter was added. No new Workspace operation, transaction lifecycle, replay dispatcher, gateway class or TypeScript tool was added.

Cycle20's legacy baseline attestation intentionally remains unchanged: it requires the historical recorded observation corpus to be present. The benchmark therefore uses the authenticated 16-input v2 fixture as its smallest comparison set and adds inputs for the 32/64 runs. This avoids broadening the acceptance behavior of v1/v2 while comparing the new table lookup path.
