# Metrics

Production runtime changes: 0 LOC. No Workspace mutation, transaction, replay, gateway, oracle-vocabulary, or TypeScript schema changes were made. New experiment generator/orchestration and reducer are 303 LOC; focused test coverage is 45 LOC. The campaign uses 3 existing canonical operation families and 3 existing gateway authorization paths; it introduces no dispatch or transaction implementation.

The primary campaign has 16 complete generated production workflows over four graph topologies; the second campaign has 8 workflows using distinct seeds; one exploratory leaf-rename workflow was added separately. Each workflow produces one atomic rename and one atomic maintenance commit containing three literal targets. Per-workflow negative proposal counts are extracted in `negative-controls.json`. Mission-specific runtime additions are zero; all generated differences live in host-owned data and experiment tooling.
