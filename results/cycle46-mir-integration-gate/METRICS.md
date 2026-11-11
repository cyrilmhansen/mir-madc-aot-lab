# Metrics

- Composite specifications: 24
- Total functions including helpers: 32
- Composition families: 6
- Independent observations: 160
- Interpreter/JIT mismatches: 0
- Fresh text observations: 160, byte-identical output
- Fresh binary observations: 160, byte-identical output
- Fresh-process repeat: 160, byte-identical output
- Optimization levels tested: 0, 1, 2, 3; 160 each, identical
- Native object GCC checks: 16 per optimization level (64)
- Native object Clang checks: 16 at level 2
- Shared-library dlopen/dlsym checks: 8
- Metamorphic local-register rename checks: 160
- Injected structural reducer cases: 2/2, each removed 3 unrelated operations
- Invalid controls: 5; four returned diagnostics, one invalid-label SIGSEGV
- Production MIR/MADC code changes: 0
- Genuine valid-program defects: 0
