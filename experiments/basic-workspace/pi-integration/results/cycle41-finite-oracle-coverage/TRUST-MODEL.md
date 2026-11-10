# Trust model

The finite table is trusted only as a host-owned expected-results artifact. The mathematical specification and evaluator live in experiment tooling, not in the agent request or Cycle20. Integrity does not prove the mathematics correct; the reports preserve the specification, input selection and table-generation path.

The continuation process binds the destination contract identity and digest in the host-anchored package. The receiver verifies the external anchor and package artifacts before it enables maintenance. A table edit in the package fails the destination-contract artifact digest; supplying a different contract file fails destination identity/digest validation. The table cannot enlarge the separately host-owned target permissions.

The gateway loads and validates its contract once at initialization, and uses that in-memory snapshot for authorization and commit revalidation. Tool requests cannot supply validation rows or mutate contract state. Candidate validation compares interpreter and JIT observations with the same trusted expected map. Structural and dependency invariants remain separate.

The finite input corpus establishes only sampled agreement. It is not universal semantic proof, and a faulty independent specification would produce faulty expected results even if correctly integrity-protected.
