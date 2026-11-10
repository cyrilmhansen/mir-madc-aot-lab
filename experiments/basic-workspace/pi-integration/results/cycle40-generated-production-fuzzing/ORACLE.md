# Independent oracle

The oracle evaluates the generated mathematical graph directly: provider value is `min(cap, max(0, x))`; each later node is `1` iff its one declared predecessor's result is at least its configured threshold. After maintenance, the cap and first predicate threshold use their separately generated replacement values. This evaluator reads the abstract specification, not Workspace projection, MIR output, replay state, or production validation responses.

The same input corpus is evaluated by the Cycle19 host creation validator, Cycle37 rename validator, Cycle20 maintenance validator, MIR interpreter, MIR JIT and fresh replay checks. Every accepted workflow has exact integer-valued observations saved in its stage evidence. Full function observations are present in each attempt's gateway evidence and revision-checkpoint files.

This is bounded boundary testing, not proof over all numeric values.
