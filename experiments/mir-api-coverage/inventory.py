#!/usr/bin/env python3
"""Inventory pinned MIR declarations, library exports, types and opcodes."""
import json, pathlib, re, subprocess, platform, hashlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
MIR = ROOT / "madc/third_party/mir"
LIB = ROOT / "madc/obj/mir/host/libmir.a"
headers = [MIR / "mir.h", MIR / "mir-gen.h", MIR / "mir-debug.h"]
declared = {}
for path in headers:
    text = path.read_text(errors="replace")
    for name in re.findall(r"\bextern\s+[^;{}]*?\b(MIR_[A-Za-z0-9_]+)\s*\(", text, re.S):
        declared.setdefault(name, []).append(path.name)
    # Header-only inline entrypoints are available to callers but need no archive symbol.
    for name in re.findall(r"\bstatic\s+inline\s+[^;{}]*?\b(MIR_[A-Za-z0-9_]+)\s*\(", text, re.S):
        declared.setdefault(name, []).append(path.name + " (inline)")
symbols = set()
if LIB.exists():
    out = subprocess.check_output(["nm", "-g", "--defined-only", str(LIB)], text=True)
    symbols = {line.split()[-1] for line in out.splitlines() if line.split()}
optext = (MIR / "mir.h").read_text()
block = optext.split("typedef enum {", 2)[1].split("} MIR_insn_code_t;", 1)[0]
ops = re.findall(r"\bINSN_EL\s*\(\s*([A-Z0-9_]+)\s*\)", block)
for macro_args in re.findall(r"REP\d+\s*\(\s*INSN_EL\s*,([^)]*)\)", block, re.S):
    ops.extend(re.findall(r"\b([A-Z][A-Z0-9_]*)\b", macro_args))
ops = list(dict.fromkeys(ops))
type_text = (MIR / "mir-type.h").read_text()
types = re.findall(r"TYPE_EL\s*\(\s*([A-Z0-9_]+)\s*\)", type_text.split("typedef enum {",1)[1].split("} MIR_type_t;",1)[0])
families = {
 "moves": [x for x in ops if x.endswith("MOV")],
 "extensions_conversions": [x for x in ops if x.startswith(("EXT","UEXT","I2","UI2","F2","D2","LD2"))],
 "arithmetic": [x for x in ops if x.startswith(("ADD","SUB","MUL","DIV","MOD","NEG"))],
 "bitwise_shifts": [x for x in ops if x in {"AND","ANDS","OR","ORS","XOR","XORS","LSH","LSHS","RSH","RSHS","URSH","URSHS"} or x.startswith(("VAND","VOR","VXOR","VLSH","VRSH","VURSH"))],
 "comparisons": [x for x in ops if x in {"EQ","EQS","NE","NES","LT","LTS","ULT","ULTS","LE","LES","ULE","ULES","GT","GTS","UGT","UGTS","GE","GES","UGE","UGES","FEQ","DEQ","LDEQ","FNE","DNE","LDNE","FLT","DLT","LDLT","FLE","DLE","LDLE","FGT","DGT","LDGT","FGE","DGE","LDGE"} or x.startswith(("VEQ","VNE","VGT","VLT","VLE"))],
 "branches_control": [x for x in ops if x in {"JMP","BT","BTS","BF","BFS","BO","UBO","BNO","UBNO","LADDR","JMPI","SWITCH","RET","JRET","LABEL"} or x.startswith(("BEQ","BNE","BLT","BLE","BGT","BGE","FBEQ","DBEQ","LDBEQ","FBNE","DBNE","LDBNE","FBLT","DBLT","LDBLT","FBLE","DBLE","LDBLE","FBGT","DBGT","LDBGT","FBGE","DBGE","LDBGE"))],
 "calls": [x for x in ops if x in {"CALL","INLINE","JCALL"}],
 "memory_stack": [x for x in ops if x in {"ADDR","ADDR8","ADDR16","ADDR32","ALLOCA","BSTART","BEND","FRAME_ADDR","RET_ADDR","VA_ARG","VA_BLOCK_ARG","VA_START","VA_END"}],
 "vector": [x for x in ops if x.startswith("V")],
 "overflow": [x for x in ops if x in {"ADDO","ADDOS","SUBO","SUBOS","MULO","MULOS","UMULO","UMULOS"}],
 "other_internal": [x for x in ops if x in {"UNSPEC","PRSET","PRBEQ","PRBNE","USE","PHI","INVALID_INSN"}]
}
familied = set(sum(families.values(), []))
families["other"] = [x for x in ops if x not in familied and x != "INSN_BOUND"]
data = {"source": "pinned checkout headers and current host libmir.a", "library": str(LIB.relative_to(ROOT)),
 "artifact_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [LIB, MIR / "mir.h", MIR / "mir-gen.h", MIR / "mir-debug.h"]},
 "current_execution_target": {"system": platform.system(), "machine": platform.machine(), "python": platform.python_version()},
 "prior_lab_target_evidence": ["Linux x86-64", "Linux AArch64 under QEMU", "macOS arm64"],
 "declared_api": [{"name":n,"headers":files,"library_exported":n in symbols,"status":"exported" if n in symbols else ("header_inline" if any("(inline)" in f for f in files) else "declared_without_library_symbol")} for n,files in sorted(declared.items())],
 "exported_mir_symbols_count": len([s for s in symbols if s.startswith("MIR_")]),
 "types": types, "instruction_count_excluding_bound": len([x for x in ops if x!="INSN_BOUND"]),
 "instructions": [{"name":x,"family":next((k for k,v in families.items() if x in v),"other"),"header_enumerated":True,"execution_support":"direct_interp_and_jit_tested" if x in {o for o in ["ADD","SUB","MUL","DIV","MOD","AND","OR","XOR","LSH","RSH","URSH","EQ","LT","ULT","GE","UGE","EXT8","UEXT8","DADD","DSUB","DMUL","DDIV","DEQ","DLT","DGE","MOV","BGE","BLT","LABEL","RET"]} else "not_probed_by_cycle42"} for x in ops if x!="INSN_BOUND"],
 "families": {k:v for k,v in families.items() if v}}
out = ROOT / "results/cycle42-mir-api-coverage/mir-api-inventory.json"
out.parent.mkdir(parents=True, exist_ok=True)
direct_api = {"MIR_init","MIR_finish","MIR_new_module","MIR_new_func","MIR_reg","MIR_new_func_reg","MIR_new_insn","MIR_new_ret_insn","MIR_new_reg_op","MIR_new_int_op","MIR_append_insn","MIR_finish_func","MIR_finish_module","MIR_new_label","MIR_new_label_op","MIR_interp_arr","MIR_load_module","MIR_gen_init","MIR_link","MIR_gen","MIR_gen_finish","MIR_output","MIR_write","MIR_read","MIR_scan_string","MIR_item_name"}
for entry in data["declared_api"]:
    entry["current_target_status"] = "available_header_inline" if entry["status"] == "header_inline" else ("available_exported_symbol" if entry["library_exported"] else "unavailable_missing_symbol")
    entry["cycle42_direct_coverage"] = "called_by_harness" if entry["name"] in direct_api else "not_called_by_new_harness"
    entry["upstream_test_coverage"] = "not_systematically_mapped_in_cycle42"
data["exported_mir_symbols"] = sorted(s for s in symbols if s.startswith("MIR_"))
out.write_text(json.dumps(data, indent=2)+"\n")
coverage = {"denominator": data["instruction_count_excluding_bound"],
            "covered": sum(x["execution_support"] == "direct_interp_and_jit_tested" for x in data["instructions"]),
            "tested_type_signatures": [
                {"instructions": ["ADD","SUB","MUL","DIV","MOD","AND","OR","XOR","LSH","RSH","URSH","EQ","LT","ULT","GE","UGE","EXT8","UEXT8"], "operands": ["MIR_T_I64","MIR_T_I64"], "result": "MIR_T_I64"},
                {"instructions": ["DADD","DSUB","DMUL","DDIV"], "operands": ["MIR_T_D","MIR_T_D"], "result": "MIR_T_D"},
                {"instructions": ["DEQ","DLT","DGE"], "operands": ["MIR_T_D","MIR_T_D"], "result": "MIR_T_I64"},
                {"instructions": ["MOV","BGE","BLT","LABEL","RET"], "operands": ["MIR_T_I64"], "result": "MIR_T_I64", "note": "bounded loop / branch labels"}],
            "type_combination_denominator": "not claimed: MIR legality is opcode and operand-slot specific; the 18 type enumerators do not form a valid Cartesian semantic matrix",
            "instructions": data["instructions"], "families": data["families"]}
(out.parent / "instruction-coverage.json").write_text(json.dumps(coverage, indent=2)+"\n")
api_lines = ["# Pinned MIR API inventory", "", f"Generated from `{MIR.relative_to(ROOT)}` and `{LIB.relative_to(ROOT)}`.",
             "", f"- Header function-like names inventoried: {len(declared)}.",
             f"- MIR-prefixed archive exports: {data['exported_mir_symbols_count']}.",
             f"- Concrete opcode enumerators: {data['instruction_count_excluding_bound']}.",
             f"- MIR type enum values: {len(types)}.", "", "## Declared API names", "",
             "| API | Header | Archive status |", "|---|---|---|"]
for entry in data["declared_api"]:
    api_lines.append(f"| `{entry['name']}` | {', '.join(entry['headers'])} | {entry['status']} |")
(out.parent / "MIR-API-INVENTORY.md").write_text("\n".join(api_lines)+"\n")
print(f"wrote {out}; declarations={len(declared)} exports={data['exported_mir_symbols_count']} opcodes={data['instruction_count_excluding_bound']} types={len(types)}")
