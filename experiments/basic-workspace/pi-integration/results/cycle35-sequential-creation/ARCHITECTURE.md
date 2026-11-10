# Cycle 35 architecture

Cycle 19 had one fixed two-mission flow and a separate mode for one constructor after a verified stream. Cycle 35 adds an explicitly selected **creation-only sequence mode to the existing `Cycle19Gateway`**. It does not add a gateway class, Workspace operation, transaction kernel, replay dispatcher, TypeScript schema, or agent tool.

Each configured step is normalized into the existing active creation contract. Constructor requests still pass through the same `_candidate` function. That code checks the exact function name/signature, that each required callee is discovered, its live portable handle resolves to a numeric callable signature, calls are bound to exactly the required handle set, and prior functions are unchanged. It uses Workspace's canonical typed constructor preview and existing portable identity allocator.

The same `_preview` and `_commit` methods call the existing `SemanticTransactionKernel`. Commit revalidates the active contract and complete candidate. After commit, the existing creation validation path checks the new function's finite expected results, all preserved functions, exact dependency edges, signature, interpreter/JIT agreement and fresh constructive replay.

New sequence-only responsibilities in `cycle19_gateway.py` are bounded contract validation, activation of the next ordered step, sequence checkpoint creation/verification, and prefix recovery. Step advancement is a trusted host-only method and is absent from `extension.ts` and the five active Pi tools. Each function commit is atomic; the complete sequence is not.

Recovery does not rely on historical Workspace snapshots, because the canonical document projection only exposes the current document revision. Instead, the adapter replays each required prefix in an isolated empty Workspace through the Cycle 31 `replay_constructive_stream`, compares normalized semantics, verifies expected bindings and finite results using both MIR engines, and then compares the final prefix against the checkpoint. No source text is used to construct the Workspace.

The old Cycle 19 two-step behavior and the one-step verified-stream creation mode remain backward-compatible and use the same existing candidate/preview/commit functions. This result supports a reusable, bounded sequence of function-creation steps; it does not claim general heterogeneous mission composition.
