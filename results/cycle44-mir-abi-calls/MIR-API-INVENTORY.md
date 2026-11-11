# MIR API inventory

`mir-api-inventory.json` carries forward the Cycle43 census of 181 API declarations across `mir.h`, `mir-gen.h` and `mir-debug.h`, with symbol availability from the checked-out `libmir.a`. It is augmented with Cycle44's direct call-family usage. Header declarations and archive symbol presence remain separate fields; inline declarations are not expected as archive exports.

Cycle44 directly exercised the `_arr` function/prototype constructors, `MIR_interp_arr`, `MIR_new_insn_arr` for MIR_CALL, `MIR_new_ret_insn`, import/export, `MIR_load_external`, module load/link, `MIR_gen`, `MIR_object_emit`, `MIR_object_emit_executable`, `MIR_object_load`, text output/scan and binary write/read. Variadic constructor counterparts were inspected but not used. `MIR_JCALL/JRET` were inspected and excluded as non-standard threaded calls.

The inventory identifies the selected host target only. Other backend declarations and architectures are not claimed exercised by Cycle44.
