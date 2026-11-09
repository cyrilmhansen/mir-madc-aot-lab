#!/usr/bin/env python3
"""Combine the two genuine Cycle 24 campaign traces without rewriting their evidence."""
from __future__ import annotations
import argparse,json,pathlib,subprocess,sys
import shutil
ROOT=pathlib.Path(__file__).resolve().parents[5]
VISUAL=ROOT/"experiments/basic-workspace/scripts/basic-visual.py"
def read(path):return json.loads(path.read_text(encoding="utf-8"))
def rows(path):return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--root",type=pathlib.Path,default=pathlib.Path(__file__).resolve().parent);a=ap.parse_args()
 root=a.root.resolve();m1=root/"mission-1-real-agent-01";m2=root/"mission-2-real-agent-01";out=root/"combined-replay";out.mkdir(parents=True,exist_ok=True)
 v1=read(m1/"mission-3-validation-host.json");v2=read(m2/"validation.json")
 if not v1.get("mission_complete") or not v2.get("mission_complete") or v1["revision"]!=6 or v2["revision"]!=7:
  raise SystemExit("Cannot build success replay from incomplete mission evidence")
 s1=read(m1/"visual-source.json");s2=read(m2/"visual-source.json")
 e1=rows(m1/"visual-events.jsonl")
 committed6=next((event.get("snapshot") for event in e1 if event.get("event_type")=="commit" and event.get("revision")==6),None)
 if committed6 is None or committed6!=s2["snapshots"].get("6"):
  raise SystemExit("Mission 1 commit snapshot and reconstructed Mission 2 revision-6 snapshot differ")
 # Cycle 19's phase-3 bundle kept only its initial source snapshot; the genuine
 # commit event is the authoritative revision-6 snapshot and is promoted here.
 snapshots={**s1["snapshots"],"6":committed6,**s2["snapshots"]}
 source={"schema":"basic-workspace.visual-source","version":1,
  "campaign":{"id":"cycle24-dependency-propagation","title":"Cycle 24 · SCORE_CLASS dependency propagation","filename":"SCORES.bas"},
  "initial":s1["initial"],"snapshots":snapshots}
 write(out/"visual-source.json",source)
 events=e1
 seq=len(events)
 m1last=events[-1] if events else {}
 session2=next((e.get("session_id") for e in rows(m2/"visual-events.jsonl") if e.get("event_type")!="initial"),"cycle24-mission-2")
 boundary={"event_id":"cycle24-fresh-pi-context-boundary","event_type":"context_reset","revision":6,
  "session_id":session2,"mission_id":"cycle24.raise-passing-threshold45.v1",
  "provenance":"Host-derived from separate mission launcher and session directories",
  "title":"Fresh Pi mission · semantic state retained",
  "description":"Mission 2 ran in a new Pi process/session after Mission 1 host validation. The committed revision-6 Workspace was rebuilt from its portable operation stream; Mission 1 conversation history was not supplied.",
  "focus":{"handles":["score_class.function","is_passing.function"],"mapping":"verified_function_boundary"},
  "dependencies":[{"caller":"IS_PASSING","callee":"CLAMP_SCORE"},{"caller":"SCORE_CLASS","callee":"CLAMP_SCORE"},{"caller":"SCORE_CLASS","callee":"IS_PASSING"}],
  "source_evidence":{"mission1_host_validation":"../mission-1-real-agent-01/mission-3-validation-host.json",
   "mission2_session":"../mission-2-real-agent-01/pi-session.jsonl","mission2_baseline_revision":6}}
 events.append(boundary);seq+=1
 for event in rows(m2/"visual-events.jsonl"):
  if event.get("event_type")=="initial":continue
  events.append(event)
 for index,event in enumerate(events,1):event["presentation_sequence"]=index
 with (out/"visual-events.jsonl").open("w",encoding="utf-8") as f:
  for event in events:f.write(json.dumps(event,ensure_ascii=False,separators=(",",":"))+"\n")
 write(out/"validation.json",v2)
 shutil.copy2(m2/"constructive-operations.json",root/"constructive-operations.json")
 shutil.copy2(m2/"equivalence.json",root/"equivalence.json")
 shutil.copy2(root/"deterministic-preflight-edge-set/function-creation/gateway-evidence/cycle21-baseline-verification.json",
  root/"cycle21-baseline-host-verification.json")
 points=[39,40,44,45,50]
 propagation={str(x):{"before_revision_6":v1["observed_results"]["interp"][str(x)],
   "before_jit":v1["observed_results"]["jit"][str(x)],
   "after_revision_7":v2["observed_results"]["interp"][str(x)],
   "after_jit":v2["observed_results"]["jit"][str(x)]} for x in points}
 write(root/"dependency-propagation.json",{"schema":"basic-workspace.cycle24-propagation-evidence","version":1,
  "direct_edit":{"function":"IS_PASSING","literal":"40 → 45","committed_revision":7},
  "indirect_behavior":{"function":"SCORE_CLASS","source_structurally_unchanged":v2.get("SCORE_CLASS_structurally_unchanged"),
   "dependency_edges_unchanged":v2.get("dependency_edges_unchanged"),"observations":propagation},
  "engine_agreement":all(row["before_revision_6"]==row["before_jit"] and row["after_revision_7"]==row["after_jit"] for row in propagation.values()),
  "source_of_before_observations":"Mission 1 host validation at revision 6",
  "source_of_after_observations":"Mission 2 host validation at revision 7"})
 write(root/"dependency-graph.json",{"schema":"basic-workspace.cycle24-dependency-graph","version":1,
  "revision_5_before_creation":[{"caller":"IS_PASSING","callee":"CLAMP_SCORE"}],
  "revision_6_after_creation":[{"caller":"IS_PASSING","callee":"CLAMP_SCORE"},
   {"caller":"SCORE_CLASS","callee":"CLAMP_SCORE"},{"caller":"SCORE_CLASS","callee":"IS_PASSING"}],
  "revision_7_after_maintenance":[{"caller":"IS_PASSING","callee":"CLAMP_SCORE"},
   {"caller":"SCORE_CLASS","callee":"CLAMP_SCORE"},{"caller":"SCORE_CLASS","callee":"IS_PASSING"}],
  "source":"Recorded semantic projections and MissionContract validation; call-site multiplicity normalized to unique graph edges"})
 write(out/"visual-evidence-view.json",{"inputs":[39,40,44,45,50],"result_keys":["clamp_score","is_passing","score_class"]})
 summary={"campaign_kind":"two genuine Pi sessions with host replay between missions",
  "mission_1":{"session":"../mission-1-real-agent-01","revision":6,"passed":True,
   "host_validation":"../mission-1-real-agent-01/mission-3-validation-host.json"},
  "mission_boundary":{"kind":"host_derived_fresh_session","workspace_revision":6,"model_transcript_reused":False},
  "mission_2":{"session":"../mission-2-real-agent-01","revision":7,"passed":True,
   "host_validation":"../mission-2-real-agent-01/validation.json"},"source_events":len(events),
  "snapshots":sorted(int(revision) for revision in snapshots),"committed_revisions":[5,6,7],
  "provenance":"Genuine model/gateway events are copied from each mission; one context-reset marker is derived from the separate launcher records."}
 write(out/"presentation-adapter-summary.json",summary)
 pi1=read(m1/"summary.json");pi2=read(m2/"summary.json")
 def model_metrics(row):
  session=row["session"]
  return {"model":row.get("model"),"turns":session.get("turn_end_events"),
   "tool_calls":session.get("tool_call_starts"),"tools_by_name":session.get("tool_calls_by_name"),
   "reported_usage":session.get("usage_reported_by_pi"),"elapsed_ms":session.get("elapsed_ms"),
   "timed_out":session.get("timed_out"),"exit_code":session.get("exit_code"),
   "agent_state":session.get("observer",{}).get("state"),"tool_schema_bytes":row.get("tool_schema_bytes"),
   "gateway_ms":row.get("gateway_tool_processing_ms")}
 campaign={"schema":"basic-workspace.cycle24-campaign-summary","version":1,
  "mission_1":{"mission_id":"cycle24.score-class.v1","base_revision":5,"result_revision":6,
   "committed":True,"host_validation_passed":bool(v1.get("mission_complete")),"metrics":model_metrics(pi1)},
  "mission_2":{"mission_id":"cycle24.raise-passing-threshold45.v1","base_revision":6,"result_revision":7,
   "committed":True,"host_validation_passed":bool(v2.get("mission_complete")),"metrics":model_metrics(pi2)},
  "aggregate":{"model_turns":sum(model_metrics(row)["turns"] or 0 for row in (pi1,pi2)),
   "tool_calls":sum(model_metrics(row)["tool_calls"] or 0 for row in (pi1,pi2)),
   "accepted_previews":2,"rejected_model_previews":1,"commits":2,"constructive_operations":6,
   "semantic_identity_remappings":v2.get("replay",{}).get("identity_remappings"),
   "interpreter_jit_and_replay_passed":bool(v1.get("mission_complete") and v2.get("mission_complete")),
   "visual_html":"combined-replay/visual-replay-generic.html"}}
 write(root/"campaign-summary.json",campaign)
 proc=subprocess.run([sys.executable,str(VISUAL),"replay",str(out),"--evidence-view",str(out/"visual-evidence-view.json")],capture_output=True,text=True)
 if proc.returncode:raise SystemExit(proc.stderr)
 print(proc.stdout.strip())
if __name__=="__main__":main()
