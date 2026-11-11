#!/usr/bin/env python3
"""Repeated same-host end-to-end process timing for Cycle43 MIR routes."""
import json
import statistics
import subprocess
import time
from pathlib import Path
root = Path(__file__).resolve().parents[2]
bin_path = root / 'experiments/mir-api-coverage/build/mir-cfg-memory'
text_path = root / 'experiments/mir-api-coverage/build/cycle43-final.mir'
binary_path = root / 'experiments/mir-api-coverage/build/cycle43-final.bmir'
routes = {
    'direct_construction_interpreter_jit': [str(bin_path), str(root / 'experiments/mir-api-coverage/build/perf.mir'), str(root / 'experiments/mir-api-coverage/build/perf.bmir')],
    'fresh_text_parse_interpreter_jit': [str(bin_path), '--text', str(text_path)],
    'fresh_binary_decode_interpreter_jit': [str(bin_path), '--binary', str(binary_path)],
}
result = {'samples_each': 7, 'warmups_each': 2, 'cases_per_run': 412, 'scope': 'end-to-end process wall time; startup and all route work included', 'routes': {}}
for name, cmd in routes.items():
    for _ in range(2):
        subprocess.run(cmd, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    samples=[]
    for _ in range(7):
        start=time.perf_counter()
        subprocess.run(cmd, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        samples.append((time.perf_counter()-start)*1000)
    result['routes'][name]={'samples_ms':[round(x,3) for x in samples], 'median_ms':round(statistics.median(samples),3), 'min_ms':round(min(samples),3), 'max_ms':round(max(samples),3)}
direct=result['routes']['direct_construction_interpreter_jit']['median_ms']
for name in ('fresh_text_parse_interpreter_jit','fresh_binary_decode_interpreter_jit'):
    result['routes'][name]['ratio_to_direct_median']=round(result['routes'][name]['median_ms']/direct,3)
result['threshold']={'registered':'2.0x median ratio', 'exceeded':any(result['routes'][n]['ratio_to_direct_median']>2.0 for n in ('fresh_text_parse_interpreter_jit','fresh_binary_decode_interpreter_jit'))}
(root/'results/cycle43-mir-cfg-memory/performance-results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
