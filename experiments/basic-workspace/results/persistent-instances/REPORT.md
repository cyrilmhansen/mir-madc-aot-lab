# Persistent MIR instances — Cycle 10B

## Result

The prototype now provides a persistent native MIR worker per execution
instance. A worker loads one revision-bound projection, builds and links its
MIR module once, then serves repeated function calls. The existing
`execute_function` path remains one-shot. Module-level numeric arrays are MIR
BSS data; initialization is a generated BASIC function run once before the
instance is published. Function-local arrays retain per-call lifetime.

The `GET_AGE` and `SET_AGE` functions are built through typed Workspace
operations and execute generated comparisons, loops and indexed MIR memory
operations. No BASIC rendering or reparsing occurs in the execution path.
Interpreter and JIT both pass the isolation scenario: instance A changes age
205 from 42 to 47, instance B remains at 42, and a newly created instance C
starts at 42. Missing ID 999 returns -1. Renaming the function creates a new
definition revision while existing instances continue to use the old
projection and state.

This is a per-instance compilation design: MIR code is reused between calls
inside one worker, but each instance builds its own copy. Runtime mutation does
not change the ProgramDefinition revision. Calls to one instance are
serialized. A timed-out or crashed worker is marked dead and is never silently
restarted; mutation rollback is not promised after a failed call.

## Protocol and lifecycle

See [PROTOCOL.md](PROTOCOL.md) for BWM5 metadata and framed requests. The
Python API in `basic_workspace.mir_execution.PersistentExecutionService`
provides opaque prepared-module and instance handles, creation, invocation,
status inspection, destruction and release. Module and instance counts are
bounded. Function IDs are resolved against the immutable module projection;
an optional initializer must return zero and runs only during creation. A
failed initializer prevents publication of a usable instance.

The worker is an isolation boundary for native state, not a general sandbox.
The current MIR data-address lowering has only been validated on the native
x86-64 host. Persistent strings, state migration, hot reload, concurrent calls
to one instance and cross-instance compiled-code sharing are not implemented.

## Reproduction and tests

From `experiments/basic-workspace`:

```sh
./scripts/build-mir-worker.sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/demo-persistent-address-book.py
python3 scripts/benchmark-persistent.py
```

The suite has **85 passing tests**, including four persistent-worker tests.
The four persistent tests also passed with Clang AddressSanitizer,
UndefinedBehaviorSanitizer and LeakSanitizer enabled. The demo tests both MIR
interpreter and JIT; it checks two-instance isolation, initializer-once,
function-local array reset, revision isolation, instance destruction and
1/10/100/1000 warm reads and writes. Raw output is in `demo.json` and
`benchmark.json`.

The benchmark is one local run, not a 30-run statistical campaign. For a
stateless `DOUBLE` function, 1,000 one-shot calls took 706.6 ms (interpreter)
and 1,043.1 ms (JIT); 1,000 persistent calls took 9.77 ms and 10.30 ms.
Persistent worker startup was 0.60 ms and 0.72 ms respectively, including
module compilation. The worker reported exactly one MIR build and link. Warm
address-book reads/writes averaged about 8 microseconds per call over 1,000
calls for both engines. RSS after warm calls was about 3.4 MiB (interpreter)
and 3.9 MiB (JIT); this short run is a spot check, not a leak proof.

The fresh-worker behavior remains available as a regression baseline.
Performance numbers include Python/native protocol round trips for persistent
calls and process startup for one-shot calls, so they describe these service
paths rather than bare MIR invocation cost.

## Ownership and remaining limits

The Workspace token model owns editable program structure. Its immutable
projection binds types, shared-array slots and function slots to a document
revision. Each native worker owns its MIR context, generated functions and
module data; process teardown releases them. Separate workers therefore have
independent arrays. The initializer's assignments are MIR code, not Python
data population.

The top-level `DIM` declaration is an explicitly restricted Workspace
extension, not a claim about historical BASIC module-global semantics. Only
fixed one-dimensional numeric arrays are persistent. No state migration is
performed when a new definition revision is prepared. Old modules may be
released only after their instances are destroyed. If a worker dies during a
state-changing call, that instance is invalid because partial mutation cannot
be ruled out.

No tests were added to or changes made in the historical BASIC compiler, MIR,
or MADC. MPDecimal log modifications at the laboratory root remain outside
this work.
