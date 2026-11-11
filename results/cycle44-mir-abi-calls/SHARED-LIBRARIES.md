# Shared libraries

MIR emitted an ELF shared library. Separate GCC and Clang clients load it with `dlopen`, resolve every matrix export through a correctly typed `dlsym` pointer, exercise internal and imported calls, validate pointer-buffer effects and call `dlclose` after all calls have completed. Both clients report zero mismatches.

The library is also omitted from the committed evidence; regeneration commands and ELF inspection output are preserved. No function pointer is used after `dlclose`.
