# Reduction

The bounded Cycle46 reducer generated valid MIR text from typed specifications and invoked a fresh process at each trial. Injection A combined EXT8, a comparison branch and three unrelated operations; it reduced from three noise operations to zero while retaining the conversion-dependent branch. Injection B combined a pointer load, EXT8, arithmetic and a bounded store; it reduced from three noise operations to zero while retaining load/conversion/store and exact expected memory bytes. Both comparator faults preserved their failure class and JIT/native function-pointer boundary. These are injected tests, not compiler defects.

The reducer only removes declared independent operation chains from these two templates. It is not a general MIR reducer. Its temporary interpreter setup issue is documented in `harness-defects.json`; final reductions use the corrected initialization/link order.
