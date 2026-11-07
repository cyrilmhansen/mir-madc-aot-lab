# Deterministic semantic editing mechanics

Tasks: 16. This compares scripted clients, not LLM behavior.

| Measure | Semantic API | Text editing |
|---|---:|---:|
| Correct tasks | 16/16 | 10/16 |
| Tool calls | 108 | 32 |
| Context bytes exposed | 35582 | 13906 |
| Harness wall time total | 581.528 ms | 0.125 ms |
| LLM trials / tokens | not run / unavailable | not run / unavailable |

This trial measures API mechanics and payload size. The text arm deliberately uses literal search/replace, so failures expose its known ambiguity; it is not an estimate of human or model performance. Historical inputs were read-only and no BASIC file was patched.

Wall time is harness mechanics only: the semantic arm starts a fresh subprocess per task, while the text arm uses in-process string operations. Do not interpret these as comparative agent latency. Token use is unavailable and recorded as null.

| Task | Semantic status | Semantic correct | Text status | Text correct |
|---|---|---:|---|---:|
| local_rename_with_decoys | committed | True | edited | False |
| case_insensitive_local_reference | committed | True | edited | False |
| function_rename | committed | True | edited | False |
| renumber_goto | committed | True | edited | True |
| renumber_gosub | committed | True | edited | True |
| renumber_on_goto | committed | True | edited | True |
| atomic_rename_and_renumber | committed | True | edited | True |
| collision_rejected | rejected_NAME_COLLISION | True | attempted | False |
| move_function | committed | True | edited | True |
| ambiguous_array_call_stop | refused | True | refused | True |
| incomplete_function_stop | refused | True | refused | True |
| colon_statement_scope | committed | True | edited | True |
| historical_fn | committed | True | edited | True |
| historical_mastermind | committed | True | edited | False |
| historical_poker | committed | True | edited | False |
| multi_agent_stale_revision | conflict_rejected | True | two_agents_conflict_simulated | True |
