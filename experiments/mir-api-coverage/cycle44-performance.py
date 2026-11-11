#!/usr/bin/env python3
"""Measure repeatable process-level Cycle44 routes (includes startup/setup)."""
import json, pathlib, statistics, subprocess, time

root=pathlib.Path(__file__).resolve().parents[2]
build=root/'experiments/mir-api-coverage/build'
results=root/'results/cycle44-mir-abi-calls'
exe=build/'mir-abi-corpus-fresh'
cases={
 'direct_build_interpreter_jit':[str(exe),'--run'],
 'fresh_text_parse_interpreter_jit':[str(exe),'--text',str(results/'program.mir')],
 'fresh_binary_decode_interpreter_jit':[str(exe),'--binary',str(results/'program.bmir')],
 'mir_object_loader':[str(exe),'--load-object',str(results/'mir-abi.o')],
 'system_linked_object_client':[str(build/'cycle44-native-client')],
 'shared_library_dlopen_client':[str(build/'cycle44-shared-client'),str(results/'libmir-abi.so')],
}
out={'method':'one warmup, seven measured fresh processes per route; wall-clock includes process startup and route setup','samples':7,'routes':{}}
for name,cmd in cases.items():
    warm=subprocess.run(cmd,cwd=root,capture_output=True,text=True,timeout=10)
    if warm.returncode: raise SystemExit(f'warmup failed {name}: {warm.stderr}')
    samples=[]
    for _ in range(7):
        start=time.perf_counter_ns(); p=subprocess.run(cmd,cwd=root,capture_output=True,text=True,timeout=10); elapsed=time.perf_counter_ns()-start
        if p.returncode: raise SystemExit(f'run failed {name}: {p.stderr}')
        samples.append(elapsed/1e6)
        out['routes'][name]={'median_ms':statistics.median(samples),'min_ms':min(samples),'max_ms':max(samples),'raw_ms':samples,'stdout_last':p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ''}
(results/'performance-results.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:{'median_ms':v['median_ms'],'range_ms':[v['min_ms'],v['max_ms']]} for k,v in out['routes'].items()},indent=2))
