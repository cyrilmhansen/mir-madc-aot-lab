#!/usr/bin/env python3
"""Extend Cycle43's pinned API census with Cycle44 call-path evidence."""
import hashlib, json, pathlib, platform, subprocess

root=pathlib.Path(__file__).resolve().parents[2]
outdir=root/'results/cycle44-mir-abi-calls'; outdir.mkdir(parents=True,exist_ok=True)
base=json.loads((root/'results/cycle43-mir-cfg-memory/mir-api-inventory.json').read_text())
apis={x['name']:x for x in base['declared_api']}
coverage={
 'MIR_new_func_arr':'direct construction of 52 scalar signatures, internal-call graph, imports and multi-result fixture',
 'MIR_new_proto_arr':'exact prototypes for direct internal and imported C calls, including 8-argument and mixed-class calls',
 'MIR_new_call_insn':'direct internal and imported calls',
 'MIR_new_jcall_insn':'declared/exported only; not executed because MIR_JCALL/JRET use the documented non-standard threading ABI',
 'MIR_new_ret_insn':'single and two-result returns',
 'MIR_new_import':'internal module and external C imports',
 'MIR_new_export':'native C-client and dlsym-visible exports',
 'MIR_load_external':'host C fixture resolution for JIT calls',
 'MIR_interp_arr':'all 52 signatures, internal calls and imported C functions',
 'MIR_link':'all direct JIT and object/shared generation paths',
 'MIR_gen':'all direct JIT and native export functions',
 'MIR_gen_object_emit':'ELF ET_REL output linked to independent GCC and Clang clients',
 'MIR_gen_object_emit_executable':'shared library output loaded by independent clients with dlopen/dlsym',
 'MIR_object_load':'52 exports plus internal, external-import, pointer-side-effect and multi-result caller checks',
 'MIR_output':'fresh text persistence roundtrip',
 'MIR_write':'fresh binary persistence roundtrip',
 'MIR_read':'fresh binary decode',
 'MIR_scan_string':'fresh text parse',
}
for name,desc in coverage.items():
    if name in apis: apis[name]['cycle44_calling_convention_coverage']=desc
base['source']='pinned MIR source subtree from MADC checkout; API census inherited from Cycle43 and augmented with Cycle44 API calls'
base['cycle44']={'archive':'checked-out archive provenance remains historically unverified; separate isolated archive built from checked-out source for confirmatory harness','apis_exercised':coverage,'target':'Linux x86-64 SysV AMD64','fresh_archive_sha256':hashlib.sha256((root/'experiments/mir-api-coverage/build/mirfresh/libmir.a').read_bytes()).hexdigest()}
(outdir/'mir-api-inventory.json').write_text(json.dumps(base,indent=2)+'\n')
def sha(p): return hashlib.sha256((root/p).read_bytes()).hexdigest()
prov={'root_commit':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),'branch':subprocess.check_output(['git','-C',str(root),'branch','--show-current'],text=True).strip(),'madc_commit':subprocess.check_output(['git','-C',str(root/'madc'),'rev-parse','HEAD'],text=True).strip(),'madc_historical_pin':'f541a7a54624869e29b01f2f30b174bc0329eea5','mir_subtree_tree':subprocess.check_output(['git','-C',str(root/'madc'),'rev-parse','HEAD:third_party/mir'],text=True).strip(),'mir_subtree_matches_historical':subprocess.run(['git','-C',str(root/'madc'),'diff','--quiet','f541a7a54624869e29b01f2f30b174bc0329eea5','HEAD','--','third_party/mir']).returncode==0,'headers_sha256':{str(p):sha(p) for p in ['madc/third_party/mir/mir.h','madc/third_party/mir/mir-gen.h','madc/third_party/mir/mir-debug.h']},'checked_out_archive_sha256':sha('madc/obj/mir/host/libmir.a'),'isolated_archive_sha256':sha('experiments/mir-api-coverage/build/mirfresh/libmir.a'),'archive_build':'GNUmakefile target libmir.a with SRC_DIR=madc/third_party/mir and BUILD_DIR=experiments/mir-api-coverage/build/mirfresh; GCC -O3 -DNDEBUG -fPIC -std=gnu11 -fno-tree-sra -fno-ipa-cp-clone -DC2MIR_PARALLEL','host':platform.platform(),'machine':platform.machine(),'gcc':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0],'clang':subprocess.check_output(['clang','--version'],text=True).splitlines()[0],'linker':subprocess.check_output(['ld','--version'],text=True).splitlines()[0],'harness_flags':'cc -std=gnu11 -O2 -Wall -Wextra -Werror; -lm -ldl -lpthread','native_client_flags':'GCC/Clang -std=gnu11 -O2 -Wall -Wextra -Werror -rdynamic; ET_REL client links -ldl','submodule_worktree_clean':not bool(subprocess.check_output(['git','-C',str(root/'madc'),'status','--porcelain'],text=True).strip())}
(outdir/'provenance.json').write_text(json.dumps(prov,indent=2)+'\n')
print(json.dumps({'apis':len(apis),'fresh_archive_sha256':prov['isolated_archive_sha256'],'submodule_clean':prov['submodule_worktree_clean']}))
