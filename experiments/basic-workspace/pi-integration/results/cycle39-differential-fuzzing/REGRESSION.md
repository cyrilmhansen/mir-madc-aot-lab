# Regression results

Baseline Cycle38: 287 Workspace tests. Cycle39 adds five focused `test_cycle39_differential.py` tests. The complete suite finished with **292 tests passing** in **118.401 seconds**.

Command: `python3 -m unittest discover -s experiments/basic-workspace/tests -v`.

All tests passed, including historical Cycle19–38 construction, maintenance, rename, replay, handoff, transaction and TypeScript/JSONL tests. Cycle39 adds no production changes. The actual result was `Ran 292 tests in 118.401s` / `OK`.
