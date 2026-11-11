# Selected native-code and ABI check

The direct MIR harness emitted one native object and exported `cfg_diamond` and `mem_store_reload64`. A separate C client, compiled with GCC in strict C11 mode, linked that object and called both functions through typed C function pointers. It checked branch results, store/reload return values, and memory bytes around the active region. The result was `AOT ABI outputs and surrounding bytes verified`. Final object size was 5,608 bytes.

This selected check does not cover `MIR_object_load`, shared-library generation, PIE/executable emission, cross-module linking, or another target. The historical MADC object-load/native-shared regression tests passed separately, but they are not evidence for these direct MIR functions. Exact commands and scope are in `abi-results.json`.
