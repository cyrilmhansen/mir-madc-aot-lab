# Cycle 32 metrics

## Method

Production LOC uses physical lines from `wc -l`; comments and blank lines count. Generated results, reports, fixtures and tests are excluded from production. Experimental scaffolding and test counts are reported separately. No production files were changed in this cycle.

## Before / after

| Metric | Before (Cycle 31 baseline) | After Cycle 32 | Evidence |
|---|---:|---:|---|
| Canonical Workspace production LOC (`basic_workspace/*.py`) | 5,330 | 5,330 | `wc -l` on top-level package modules |
| Audited Pi integration core LOC (six files listed in AUDIT.md) | 3,951 | 3,951 | `wc -l`; preflight and generated reports excluded |
| `portable_replay.py` LOC | 439 | 439 | `wc -l` |
| Independent portable replay dispatch implementations | 1 | 1 | Explicit dispatcher in `basic_workspace/portable_replay.py` |
| Canonical operation families reused | 3 for the prospective mission: create, rename, numeric literal edit | 3 | Cycle 31 dispatcher |
| New operation families / transaction lifecycles / replay mechanisms | 0 / 0 / 0 | 0 / 0 / 0 | No code added |
| New mission-specific production runtime LOC | 0 | 0 | No gateway or policy code added |
| New production abstractions/classes | 0 | 0 | No code added |
| Cycle 32 tests added | 0 | 0 | Stop rule triggered before implementation |
| Cycle 32 report/scaffold LOC | 484 at initial report set; 41 lines of regression/bridge records added afterward | 525 total current evidence LOC | `wc -l` over the Cycle 32 report files; report/log data excluded from production LOC |

## Runtime measurements

Mission construction, maintenance, replay, MIR oracle, and TypeScript-to-JSONL Cycle 32 mission timings: **not run**. The pre-registered production authorization blocker stopped mission execution before any constructed candidate or gateway timing could be measured. Existing Cycle 23 and regression suite checks are reported separately; they do not stand in for Cycle 32 mission support.

## Interpretation

The marginal production cost for a faithful Cycle 32 production mission is not zero: the existing production path is not configurable enough. It is also not measured by adding the size of a hypothetical adapter, because this cycle's stop rule forbids introducing one. The falsification condition is met by the existing gateway assumptions. Typed representation and replay are reusable; mission authorization, multi-step orchestration, and independent oracle configuration are not yet sufficiently generic.
