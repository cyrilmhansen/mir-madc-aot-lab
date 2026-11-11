# Native objects

MIR emitted an x86-64 ELF relocatable object containing the matrix exports, internal call graph and imported C call wrappers. A separately compiled GCC client and a separately compiled Clang client linked the object and invoked all 52 matrix functions through their exact prototypes. Both reported zero mismatches. They also exercised internal calls, imported integer/mixed functions and bounded pointer writes.

`object-inspection.txt` records ELF header, symbol and relocation tables. Successful link alone was not treated as runtime proof; the clients compare numerical values and pointer canaries. The object file itself is reproducible and is not retained in the final evidence directory.
