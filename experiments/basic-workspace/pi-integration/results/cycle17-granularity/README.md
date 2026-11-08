# Cycle 17 artifacts

`AUDIT.md` documents the two authoring representations and schema measurements. `REPORT.md` reports the genuine A/B sessions, independent verification and conclusions.

Each arm directory contains the actual Pi transcript, exact active tool schemas, mission/gateway journal, constructive committed operation stream, independent validation, and offline/live presentation artifacts. The incremental arm additionally keeps the temporary ordered operation history separately from the constructive stream.

The three `preflight-*` directories contain deterministic Pi 1.5 schema and tool inventory captures. They are not model activity. `pre-registration.json` records the common task, provider/model, limits and success criteria before the two sessions.

Run `./reproduce.sh` from this directory to run the Workspace suite and regenerate both offline HTML reports. This does not invoke a model. `visual-replay-generic.html` opens locally without a server.

The original one-shot model runs are preserved in `arm-a-atomic/` and `arm-b-incremental/`; do not rerun them as part of ordinary reproduction. They are one successful A/B pair, not a repeatable benchmark.
