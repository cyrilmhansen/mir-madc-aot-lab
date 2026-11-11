# Native execution

MIR emitted ELF x86-64 ET_REL objects at optimizer levels 0–3. A separately compiled C client with typed prototypes passed 16 checks at each level. GCC and Clang clients each passed at level 2. A MIR-emitted shared library was loaded in a separate C process using `dlopen`/`dlsym`; eight calls and memory observations passed, followed by `dlclose`. The checked return values and memory bytes are in `native-gcc.txt`, `native-clang.txt`, and `shared-client.txt`.

A composite `MIR_object_load` run and PIE executable run were not performed. Cycle44 loader success applies to its own compatible artifact, not this Cycle46 composition.
