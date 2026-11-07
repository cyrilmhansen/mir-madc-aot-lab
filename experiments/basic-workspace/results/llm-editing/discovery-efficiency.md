# Compact semantic discovery

Deterministic mechanics comparison over the same 16 tasks; not LLM behavior. Exact-name unique lookup returns a symbol summary, scope/type, reference count, revision and diagnostic counts. Full references are requested only where the legacy arm asks for them.

| Interface | Calls | Request bytes | Response bytes |
|---|---:|---:|---:|
| Cycle-2 query sequence | 90 | 31631 | 64680 |
| Compact exact discovery | 59 | 26336 | 19279 |

Calls fell 34.4% and response bytes fell 70.2%. Transaction preview/commit results were unchanged.

| Response method | Legacy bytes | Compact bytes |
|---|---:|---:|
| apply_transaction | 3348 | 3348 |
| find_references_page | 4922 | 0 |
| get_diagnostics | 326 | 326 |
| get_document_structure_page | 19909 | 0 |
| list_symbols_page | 28413 | 7843 |
| open_document_from_string | 3226 | 3226 |
| preview_transaction | 4536 | 4536 |
