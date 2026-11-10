#!/usr/bin/env python3
"""Reduce one stale-revision negative while retaining the Cycle19 TS boundary."""
from __future__ import annotations
import argparse, json, os, pathlib, subprocess, sys, time
HERE=pathlib.Path(__file__).resolve().parent; ROOT=HERE.parent
sys.path[:0]=[str(ROOT),str(HERE)]
import cycle36_preflight as c36
from run_cycle16 import gateway_call

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();out=a.output.resolve()
 if out.exists() and any(out.iterdir()): raise SystemExit(f'refusing overwrite: {out}')
 out.mkdir(parents=True,exist_ok=True)
 name='REDUCED_STALE_TARGET'; handle='reduced_stale.function'; inputs=[-1,0,1]
 body=[{'kind':'assign','target':{'kind':'result'},'expression':{'kind':'local_ref','name':'X'}}]
 expected={str(x):{name.lower():float(x)} for x in inputs}
 step={'step_id':'minimal-step','mission_id':'cycle40.reducer.minimal','expected_base_revision':1,
   'function':{'name':name,'portable_handle':handle,'parameters':['X'],'return_type':'numeric'},
   'required_callees':[],'required_dependency_edges':[],'required_existing_function_handles_unchanged':[],
   'validation':{'inputs':inputs,'expected_results':expected}}
 contract={'schema':'basic-workspace.numeric-function-creation-sequence','version':1,
   'sequence_id':'cycle40.reducer.stale-revision.v1','objective':'Minimal host-owned fixture for stale revision rejection.',
   'execution_profile_id':c36.PROFILE,'starting_revision':1,'maximum_steps':1,'steps':[step]}
 cp=out/'sequence.json'; c36.write(cp,contract); evidence=out/'gateway-evidence'; err=(out/'gateway.stderr.log').open('w')
 env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join((str(ROOT),str(HERE),env.get('PYTHONPATH','')))
 proc=subprocess.Popen([sys.executable,str(HERE/'cycle19_gateway.py'),'--output',str(evidence),'--port','0','--creation-sequence',str(cp)],
  stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=err,text=True,env=env)
 try:
  ready=json.loads(proc.stdout.readline()); args={'expected_revision':1,'name':name,'parameters':['X'],'body':body}
  stale={**args,'expected_revision':0}
  result=c36.dispatch(ready,{'authoring_mode':'atomic_create','correlation_id':f'cycle40-reducer-{time.time_ns()}',
    'preview_args':args,'controls':[stale],'commit':True},out/'dispatch','atomic_create')
  row=result['controls'][0]
  if row.get('code')!='STALE_REVISION' or row.get('revision_unchanged') is not True or row.get('authoritative_workspace_changed') is not False:
   raise RuntimeError(f'minimized stale-revision failure changed class/state: {row}')
  receipt=gateway_call('127.0.0.1',ready['port'],'host_validate',{'expected_revision':2})
  if not receipt.get('mission_complete'): raise RuntimeError('Minimal reducer fixture did not remain valid after the rejected request')
  c36.write(out/'reduction.json',{'original_failure_class':'Cycle19 TypeScript constructor stale revision',
   'reduced_failure_class':row['code'],'class_preserved':True,'original_shape':'generated clamp constructor with three statements and boundary corpus',
   'reduced_shape':'one function, one result assignment, three inputs, one stale expected_revision field',
   'trust_boundary_preserved':'actual Cycle19 TypeScript handler -> JSONL -> Python gateway',
   'rejection_observation':row,'accepted_control_commit_revision':2,'host_validation_after_control':True,
   'was_injected_test_control_not_product_bug':True})
  print(json.dumps({'classification':row['code'],'reduced':True,'boundary':'Cycle19 TypeScript/JSONL'}))
 finally:
  if proc.poll() is None: proc.terminate(); proc.wait(timeout=5)
  err.close()
if __name__=='__main__': main()
