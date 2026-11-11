#!/usr/bin/env python3
"""Run bounded malformed-MIR parser controls in isolated child processes."""
import json, pathlib, subprocess, sys

exe=pathlib.Path(sys.argv[1]).resolve(); out=pathlib.Path(sys.argv[2])
specs=[]
for i in range(8): specs.append(("unknown_opcode",f"bad_opcode_{i} r, x"))
for op in ["add","sub","mul","and","or","xor"]: specs.append(("wrong_arity",f"{op} r, x"))
for i in range(6): specs.append(("undeclared_register",f"add r, ghost_{i}, 1"))
for i in range(4): specs.append(("invalid_output_lvalue",f"add {i+1}, x, 2"))
for ret in ["ret", "ret x, x", "ret x, x, x", "ret x, x, x, x"]: specs.append(("return_signature",ret))
for line in ["@", "???", "func", "endmodule unexpected"]: specs.append(("malformed_syntax",line))
rows=[]
for n,(category,line) in enumerate(specs):
    text=f"m{n}: module\nf{n}: func i64, i64:x\n  local i64:r\n  {line}\n  ret r\n  endfunc\n  endmodule\n"
    try:
        p=subprocess.run([str(exe),text],text=True,capture_output=True,timeout=3)
        result={"case_id":f"invalid_{n:02}","expected_category":category,"input":text,"returncode":p.returncode,"signal":-p.returncode if p.returncode<0 else None,"stdout":p.stdout,"stderr":p.stderr,"rejected":p.returncode!=0}
    except subprocess.TimeoutExpired as e:
        result={"case_id":f"invalid_{n:02}","expected_category":category,"input":text,"timeout":True,"stdout":e.stdout,"stderr":e.stderr,"rejected":False}
    rows.append(result)
out.write_text(json.dumps({"cases":rows,"summary":{"total":len(rows),"rejected":sum(x["rejected"] for x in rows),"accepted":sum(not x["rejected"] for x in rows),"timeouts":sum(x.get("timeout",False) for x in rows)}},indent=2)+"\n")
print(json.dumps({"total":len(rows),"rejected":sum(x["rejected"] for x in rows),"accepted":sum(not x["rejected"] for x in rows)}))
