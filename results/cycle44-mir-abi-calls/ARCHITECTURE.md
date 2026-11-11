# Architecture

`cycle44-abi-matrix.py` freezes typed signatures and emits exact-prototype C wrappers, independent weighted references, argument fillers and a separate native client. `mir-abi-corpus.c` constructs MIR through its public APIs, executes typed cases in the interpreter and JIT, and provides separate modes for text parse, binary decode, object/shared emission and object loading. The mathematical C reference is not derived from MIR observations.

The native client uses declared C prototypes for static ELF linking and correctly typed function pointers for `dlsym`. The object and shared routes use MIR-emitted machine code; the importer fixture is an independently compiled C implementation linked into the client executable and exported with `-rdynamic`. The object-loader resolver is explicit and has a negative mode that withholds one import.

No MADC frontend, BASIC Workspace gateway, custom ABI emulator or production compiler change is involved. Build tools and generated binaries live under the ignored experiment build directory; evidence stores compact results and object inspections.
