# Generator

`cycle41_v3_production_campaign.py` adapts the existing Cycle39 seeded template generator and independent evaluator. It generates the supported constructors, host creation-sequence contracts, rename contracts, exact typed edit paths and finite validation rows. The pre-registered production cases run through the existing Cycle19, Cycle37 and Cycle20 TypeScript/JSONL handlers and reuse Cycle36/38 handoff tooling. The mathematical fixture remains separate from Workspace and MIR values.

The frozen primary and secondary seed offsets are in `campaign-config.json`. A later amendment runs the four priority families with three authorized literal targets after inspection showed three targets were representable. Original two-target runs are retained as earlier attempts; amended runs are reported separately and do not overwrite them.

The generator rejects cases whose editable node is not a direct nonnegative numeric literal or whose input set exceeds the v3 limit. Such rejections are capability classifications, not passing product tests. No syntax, dispatcher or operation vocabulary is generated outside the existing typed schemas.
