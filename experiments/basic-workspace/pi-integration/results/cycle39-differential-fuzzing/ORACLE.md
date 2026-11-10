# Independent mathematical oracle

Each generated case carries a small declarative specification: function definitions refer to parameter values, integer constants, comparisons, ordered result assignments, and already-defined dependency names. The test-only evaluator interprets those specification records directly using Python integer arithmetic and ordered assignment semantics.

It does not import or call Workspace execution, projection evaluation, MIR, or portable replay. Expected outputs are computed before applying operations. The same output corpus is then compared independently against MIR interpreter, MIR JIT and freshly replayed Workspace instances.

Metamorphic observations (bounds, rename invariance, edit inversion, replay determinism and provider propagation) are stored separately and do not replace direct oracle comparisons. Exact integer-valued results are compared as floats only at the MIR numeric API boundary, with exact equality expected for this integer corpus.
