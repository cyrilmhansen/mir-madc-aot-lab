# Regression results

- Cycle42 direct corpus rerun against current available archive: 353/353 direct; 353/353 fresh text; 353/353 fresh binary. Result streams identical.
- Cycle43 corpus: 412/412 direct interpreter/JIT; 412/412 text interpreter/JIT; 412/412 binary interpreter/JIT; 412/412 second direct run. Streams identical.
- GCC strict-warning build: pass (`-Wall -Wextra -Werror`).
- Clang strict-warning build: 412 cases pass.
- UBSan build: 412 cases pass with no report.
- MADC `test_object_load`: 9 cases, 142 assertions passed. It printed expected diagnostics for malformed/legacy object inputs.
- MADC `test_native_shared`: 5 cases, 169 assertions passed.
- BASIC Workspace pytest: 303 passed, 148 subtests passed.
- Selected generated native object + separate C ABI client: pass.
- Strict C11 direct header compile: expected failure without `<stdarg.h>`; pass when preincluded, both GCC and Clang.

The MADC checkout remained clean and unchanged. The archive's exact build provenance remains unknown.
