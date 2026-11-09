# Cycle 32 mission registration (frozen before execution)

Status: pre-registered; no model inference authorized or performed.

## Initial Workspace program

Start from an empty numeric Workspace document. Construct four one-parameter numeric functions, in this order, using typed `create_numeric_function` operations:

1. `BASE_CHARGE(X) = 5 + 2 * X`.
2. `EARLY_REBATE(X) = 3 if X < 8, otherwise 0`.
3. `RUSH_SURCHARGE(X) = 7 if X >= 12, otherwise 0`.
4. `TOTAL_CHARGE(X) = BASE_CHARGE(X) - EARLY_REBATE(X) + RUSH_SURCHARGE(X)`.

Portable handles are assigned by the host independently of Workspace UUIDs:
`base_charge.function`, `early_rebate.function`, `rush_surcharge.function`, and `total_charge.function`. The parameters use corresponding `.parameter.id` handles. `TOTAL_CHARGE` calls exactly the three provider handles, with compatible one-number signatures.

With one committed constructor per Workspace transaction, the empty document begins at revision 1 and construction ends at revision 5.

## Maintenance scope

Starting at revision 5, perform the following semantic changes, preserving `TOTAL_CHARGE` structurally:

1. Rename `EARLY_REBATE` to `ADVANCE_REBATE` through its stable portable function identity; bound calls continue resolving to that same symbol.
2. Change the `RUSH_SURCHARGE` threshold from 12 to 15.
3. Change the `BASE_CHARGE` multiplier from 2 to 3.

For a prospective portable history, the rename is one revision-checked transaction (revision 6), and the two literal replacements are one atomic multi-target edit transaction (revision 7). This transaction grouping was chosen before any experiment. The literal operation contains two independently identified targets, each guarded by its expected original value.

Final semantics:

`TOTAL_CHARGE(X) = 5 + 3*X - (3 if X < 8 else 0) + (7 if X >= 15 else 0)`.

No declaration, function, parameter, array, control-flow construct, or dependency edge may otherwise be changed. Maintenance allocates or retires no semantic identity. The rename preserves the existing `early_rebate.function` identity and all call bindings. `TOTAL_CHARGE`'s normalized typed definition is invariant.

## Independent oracle inputs

`[-1, 0, 1, 7, 8, 11, 12, 14, 15, 16, 20, 50]`.

The host oracle is independently expressed as arithmetic and conditional functions, not derived from Workspace projections, replay logic, or either MIR engine. Every declared function is to be checked in both MIR interpreter and JIT against the oracle, both before and after maintenance. Final boundary expectations include: rebate applies for `X < 8`; initial surcharge starts at 12; maintained surcharge starts at 15.

## Pre-registered stop rule

No new mission runtime, dispatch branch, transaction lifecycle, mutation operation, or replay operation may be introduced. If the existing production gateway and bridge cannot authorize the entire multi-transaction mission from the empty document through configuration and already supported entry points, stop at that blocker. Direct Workspace calls or replay can establish representability only; they do not count as production-gateway support. No inference, Pi launch, or Sushi request is part of this cycle.
