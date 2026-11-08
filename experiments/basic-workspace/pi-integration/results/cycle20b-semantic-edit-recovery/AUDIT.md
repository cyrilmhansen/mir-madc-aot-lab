# Cycle 20B transport and semantic-edit audit

## Verified baseline

The campaign reconstructed the two committed Cycle 19B constructors in a new Workspace, reached revision 3, matched the recorded checkpoint and normalized structure, and validated the existing `CLAMP_SCORE` → `IS_PASSING` binding before inference. Baseline MIR interpreter/JIT behavior matched.

## Transport boundary

Pi supplies its tool-call ID to the TypeScript `execute` handler separately from the tool's argument object. The extension now forwards that correlation value in the JSONL envelope as `transport.tool_call_id`; it forwards only user-authored typed arguments in `params`. The Python bridge validates the transport envelope against a small whitelist and gives only `params` to the semantic gateway. Unknown fields inside semantic arguments still fail closed. Correlation IDs remain available in gateway timing records.

## Empty semantic paths

A root expression path is the empty list `[]`, distinct from a missing `expression_path` field. The field remains required. The actual TypeBox schema accepts `[]` for an assignment RHS and rejects the absent field; gateway validation has the same distinction.

## Actual extension-to-gateway exercise

`cycle20b_dispatch_probe.ts` imports and registers the production extension handlers, validates their actual TypeBox schemas, invokes those handlers with Pi-shaped tool-call IDs, and sends requests over the production JSONL bridge. `cycle20b_preflight.py` runs that probe against fresh Cycle 20 Gateway processes. This exercises Pi extension registration/handler logic and Python JSONL dispatch without model inference. The independent Pi inventory preflight separately captured the live Pi 1.5 tool schemas. Deterministic preflight does not establish that a model will choose valid arguments; that is tested by the separately preserved real run.

Four exact valid proposals extracted from Cycle 20's genuine tool-call records passed schema validation and previewed without changing revision 3. Each candidate changed exactly the two intended literal tokens and had interpreter/JIT agreement. The original fifth request remains a negative fixture: TypeBox rejects it because `expression_path` is missing. A known-good candidate was previewed, atomically committed in a disposable Workspace, independently validated, and replayed.

## Evidence correction

The first post-run classifier required Cycle 19's `boundary_oracle` field and consequently mislabeled the Cycle 20 validation as failed. The preserved validation record explicitly reports mission completion, matching values, interpreter/JIT agreement, and successful replay. The lifecycle classifier was corrected and regression-tested against both validation shapes. The genuine Pi transcript, original summary, and original gateway history remain unchanged; `completion-classification-correction.json` records the derived corrected state.

The initial Cycle 20B visual events also inherited the hard-coded session label `cycle20-real-agent-01`. The gateway now derives the session label from its output identity. For this completed run only the derived presentation events were relabeled to `cycle20-real-agent-02`; the original derived file is retained as `visual-events-original-session-label.jsonl`. Raw Pi and gateway records were not edited.
