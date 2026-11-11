# Failure ledger

No MIR defect was confirmed. Three harness findings were preserved:

1. **Duplicate local register names.** Initial weighted MIR construction reused `tmp`; MIR rejected duplicate declarations. The generator now names temporaries by argument position. Classification: fixture-construction defect.
2. **Double copied with integer MOV.** A generated double body used `MIR_MOV` for a D register. MIR correctly rejected the operand mode. The initial suspicion of a header/archive enum mismatch was withdrawn after the isolated source build reproduced the diagnostic and MIR output showed `mov tmp0, a0`. The fixture now uses `MIR_DMOV`. Classification: fixture-generation defect.
3. **Object-loader mixed-import expectation mismatch.** The test wrapper called with doubles `(1,2,3,4)` but the first expected value used `(0.5,1.5,2.5,3.5)`. Instrumentation showed the C helper received the actual declared arguments, and the expected calculation was corrected. Classification: oracle-fixture defect, not ABI divergence.

The earlier failures and corrected outputs are represented by the final `direct-run`, `text-run`, `binary-run` observations and `object-loader.txt`; the first transient stdout diagnostics were not preserved as standalone compiler logs. The original bad object-loader expected formula is recorded here explicitly to prevent it being mistaken for a product issue.

The missing-import case is an expected negative result. No unexpected interpreter/JIT, serialization, native link, shared-load or object-loader mismatch remains.
