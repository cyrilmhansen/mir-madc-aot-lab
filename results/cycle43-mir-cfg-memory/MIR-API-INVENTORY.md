# MIR API inventory (Cycle42 source census, Cycle43 use)

The pinned-source inventory in `mir-api-inventory.json` derives from the checked-out headers and actual `libmir.a`. It records declarations, exported symbols, inline header functions, target availability, and the limits of upstream/lab test mapping. There are 248 enumerated concrete instruction codes excluding the bound sentinel; MIR's 18 type enumerators are not a valid Cartesian opcode/type matrix.

Cycle43 directly uses `MIR_init`, module/function/register/label/operand/instruction constructors, `MIR_new_mem_op`, append/finish APIs, `MIR_interp_arr`, `MIR_gen_init`, `MIR_link`, `MIR_gen`, text output/scan, and binary write/read. Selected native code uses object mode, `MIR_gen_object_emit`, then a separately compiled C client.

Header declaration does not imply archive export: the reused census records `MIR_get_global_item` as the non-inline declaration without an exported definition. `MIR_object_load` exists in the broader lab test history, but Cycle43 does not count it as exercised by the selected external-link path.

Current-target results apply only to Linux x86-64. Historical AArch64/QEMU and macOS evidence is referenced in the Cycle42 inventory and is not new Cycle43 coverage.
