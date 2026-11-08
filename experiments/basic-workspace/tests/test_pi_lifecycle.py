import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("pi_lifecycle_test",ROOT/"pi-integration/pi_lifecycle.py")
MOD=importlib.util.module_from_spec(SPEC);assert SPEC and SPEC.loader;sys.modules[SPEC.name]=MOD;SPEC.loader.exec_module(MOD)

class PiLifecycleTests(unittest.TestCase):
    def test_completion_dimensions_keep_validated_program_separate_from_timeout(self):
        validation={"mission_complete":True,"engines_agree":True,"boundary_oracle":{"passed":True},"replay":{"passed":True}}
        result=MOD.completion_states(committed=True,validation=validation,timed_out=True,exit_code=None,
            agent_end_seen=False,agent_settled_seen=False)
        self.assertEqual(result,{"semantic_program":"passed","mission_authorization":"authorized",
            "program_commit":"committed","host_validation":"passed","pi_agent_session":"incomplete_or_unobserved",
            "launcher_process":"timed_out"})

    def test_completion_classifier_accepts_cycle20_mission_oracle_shape(self):
        # Cycle 20 records mission-specific checks (and replay), rather than
        # Cycle 19's boundary_oracle object. The common completion contract is
        # still independently host-owned.
        validation={"mission_complete":True,"engines_agree":True,"values_match":True,
            "CLAMP_SCORE_matches_cap50_semantics":True,
            "IS_PASSING_all_zero_on_test_domain":True,
            "replay":{"passed":True}}
        result=MOD.completion_states(committed=True,validation=validation,timed_out=False,
            exit_code=0,agent_end_seen=True,agent_settled_seen=True,
            authorization_status="authorized")
        self.assertEqual(result["semantic_program"],"passed")
        self.assertEqual(result["host_validation"],"passed")
        self.assertEqual(result["program_commit"],"committed")

    def test_completion_classifier_rejects_mission_oracle_mismatch(self):
        validation={"mission_complete":True,"engines_agree":True,"values_match":False,
            "replay":{"passed":True}}
        result=MOD.completion_states(committed=True,validation=validation,timed_out=False,
            exit_code=0,agent_end_seen=True,agent_settled_seen=True)
        self.assertEqual(result["semantic_program"],"failed")
        self.assertEqual(result["host_validation"],"failed")

    def test_timeout_without_commit_is_not_semantic_failure_claim(self):
        result=MOD.completion_states(committed=False,validation=None,timed_out=True,exit_code=None,
            agent_end_seen=False,agent_settled_seen=False)
        self.assertEqual(result["semantic_program"],"not_validated")
        self.assertEqual(result["host_validation"],"not_run")
        self.assertEqual(result["program_commit"],"not_committed")
        self.assertEqual(result["pi_agent_session"],"incomplete_or_unobserved")
        self.assertEqual(result["launcher_process"],"timed_out")

    def test_exit_and_agent_completion_are_independent(self):
        settled=MOD.completion_states(committed=True,validation=None,timed_out=False,exit_code=0,
            agent_end_seen=True,agent_settled_seen=True)
        ended=MOD.completion_states(committed=True,validation=None,timed_out=False,exit_code=0,
            agent_end_seen=True,agent_settled_seen=False)
        exited=MOD.completion_states(committed=False,validation=None,timed_out=False,exit_code=0,
            agent_end_seen=False,agent_settled_seen=False)
        self.assertEqual(settled["pi_agent_session"],"completed")
        self.assertEqual(ended["pi_agent_session"],"ended_not_settled")
        self.assertEqual(exited["pi_agent_session"],"incomplete_or_unobserved")
        self.assertEqual(exited["launcher_process"],"exited_normally")

    def test_duplicate_tool_boundaries_do_not_duplicate_pending_calls(self):
        observer=MOD.PiEventObserver()
        start={"type":"tool_execution_start","toolCallId":"call-1","toolName":"discover"}
        first=observer.observe(start,wall_utc="2026-01-01T00:00:00Z",monotonic_ns=10)
        duplicate=observer.observe(start,wall_utc="2026-01-01T00:00:01Z",monotonic_ns=20)
        self.assertFalse(first["duplicate_boundary"])
        self.assertTrue(duplicate["duplicate_boundary"])
        self.assertEqual(observer.state()["pending_tools"],{"call-1":"discover"})
        observer.observe({"type":"tool_execution_end","toolCallId":"call-1","toolName":"discover"},monotonic_ns=30)
        self.assertEqual(observer.state()["pending_tools"],{})

    def test_lifecycle_metadata_is_ordered_and_excludes_delta_content(self):
        observer=MOD.PiEventObserver()
        rows=[{"type":"agent_start"},{"type":"message_start","message":{"role":"assistant","model":"m"}},
              {"type":"message_update","assistantMessageEvent":{"type":"text_delta","delta":"private text"}}]
        observed=[observer.observe(row,wall_utc=f"2026-01-01T00:00:0{i}Z",monotonic_ns=i+1) for i,row in enumerate(rows)]
        self.assertEqual([x["seq"] for x in observed],[1,2,3])
        self.assertEqual(observer.state()["state"],"assistant_stream_open")
        self.assertNotIn("private text",json.dumps(observed))
        self.assertEqual(observed[-1]["delta_chars"],12)

    def test_bounded_runner_records_timeout_and_stream_arrival_without_secrets_in_metadata(self):
        script=("import json,sys,time; "
            "rows=[{'type':'agent_start'},{'type':'message_start','message':{'role':'assistant'}},"
            "{'type':'message_update','assistantMessageEvent':{'type':'text_delta','delta':'secret-content'}}]; "
            "[print(json.dumps(r),flush=True) for r in rows]; time.sleep(5)")
        with tempfile.TemporaryDirectory(prefix="atlas-pi-lifecycle-",dir="/var/tmp") as d:
            root=Path(d); stderr=(root/"stderr").open("w")
            result=MOD.run_pi_observed([sys.executable,"-c",script],env={},timeout_seconds=0.2,
                raw_event_path=root/"raw.jsonl",lifecycle_path=root/"observed.jsonl",stderr_file=stderr,
                no_progress_seconds=0.04,shutdown_grace_seconds=0.2)
            stderr.close()
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["observer"]["state"],"assistant_stream_open")
            self.assertFalse(result["pending_tool_ids"])
            self.assertIn("secret-content",(root/"raw.jsonl").read_text())
            self.assertNotIn("secret-content",(root/"observed.jsonl").read_text())
            records=[json.loads(line) for line in (root/"observed.jsonl").read_text().splitlines()]
            self.assertTrue(any(row["record_type"]=="no_progress_interval" for row in records))
            self.assertTrue(any(row["record_type"]=="launcher_timeout" for row in records))
            self.assertTrue(any(row["record_type"]=="pi_process_exit" for row in records))

    def test_agent_settled_is_visible_even_if_launcher_later_times_out(self):
        script=("import json,time; "
            "[print(json.dumps({'type':t}),flush=True) for t in ('agent_start','agent_end','agent_settled')]; time.sleep(3)")
        with tempfile.TemporaryDirectory(prefix="atlas-pi-settled-",dir="/var/tmp") as d:
            root=Path(d); statuses=[]; stderr=(root/"stderr").open("w")
            result=MOD.run_pi_observed([sys.executable,"-c",script],env={},timeout_seconds=0.5,
                raw_event_path=root/"raw.jsonl",lifecycle_path=root/"observed.jsonl",stderr_file=stderr,
                on_status=lambda state,info: statuses.append(state),no_progress_seconds=1,shutdown_grace_seconds=0.1)
            stderr.close()
            self.assertTrue(result["timed_out"])
            self.assertTrue(result["agent_settled_seen"])
            self.assertIn("agent_session_completed",statuses)

if __name__=="__main__":unittest.main()
