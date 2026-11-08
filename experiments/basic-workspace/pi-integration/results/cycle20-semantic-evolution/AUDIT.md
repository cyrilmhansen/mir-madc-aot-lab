# Cycle 20 semantic-edit feasibility audit

## Baseline replay gate

The source stream is the two committed `create_numeric_function` operations in Cycle 19B's `constructive-operations.json`. Replaying them into an empty document gives revision 3. The first operation is checked against the revision-2 recovery checkpoint fingerprint before applying the second operation; the full revision-3 normalized projection is compared with the genuine Mission 2 commit snapshot and its recorded interpreter/JIT observations. The replay maps the original function, parameter, and assignment statement identities to fresh Workspace IDs.

The baseline stream has portable parameter handles ending in `.parameter.id`, including `clamp_score.parameter.id`, although the declared BASIC parameter is named `X`. This is an existing generic alias convention inherited from constructor helpers. Cycle 20 preserves it for replay compatibility; it does not claim that the handle suffix is the source parameter name.

## Existing edit API and limitation

`Workspace.edit_assignment_expression` is authoritative and revision-bound, but replaces an entire assignment RHS. It cannot target a literal nested inside an IF comparison. The `IF` control node has no independent stable statement ID: the existing statement index assigns IDs to assignments, anchored to their target tokens. Numeric literals likewise have no stable semantic handle.

In the verified CLAMP_SCORE projection the two cap values are:

- the numeric right operand of the second top-level IF comparison, at the verified function/control path `body[1]`, expression child `[1]`;
- the numeric root of the result assignment in that IF's THEN block, identified by `clamp_score.statement.2` and expression path `[]`.

The new `edit_numeric_literal_at_path` transaction primitive is deliberately bounded to these typed locations: an assignment RHS root or the right numeric operand of a two-operand IF comparison. It resolves a numeric leaf through the current immutable typed projection, checks its expected old value, maps the supported expression shape to its canonical numeric token, edits only that token's text, then reindexes and validates the candidate. The Gateway requires both exact targets in one Workspace transaction.

The IF target is identified by the stable CLAMP_SCORE function identity plus an ordered control-flow path and expression path, not by a fabricated IF statement ID. The assignment target uses its stable statement identity. Replacing token text preserves both numeric token UIDs in the live Workspace. Existing function, parameter, and assignment statement IDs remain unchanged; the numeric literal has no semantic entity ID to preserve.

## Mission boundary

The MissionGateway compares the complete normalized candidate against a copy of the base projection with only the two approved literal values changed. It separately requires the IS_PASSING function and the semantic call edge `IS_PASSING → CLAMP_SCORE` to remain unchanged. It runs the preview candidate through both MIR engines on the specified finite corpus for impact reporting, then repeats revision and candidate authorization immediately before commit.

The policy is enforced only by the loopback Gateway used for this experiment. It is not an operating-system security boundary. The renderer is display-only and rendered BASIC is never used as edit or replay input.
