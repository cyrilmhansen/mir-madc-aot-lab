import importlib.util
import json
import sys
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
SPEC = importlib.util.spec_from_file_location("visualization", SCRIPT_DIR / "visualization.py")
VIS = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = VIS
SPEC.loader.exec_module(VIS)

CAMPAIGN = ROOT / "results" / "semantic-replay" / "longitudinal-01" / "calibrated-resume-02"


class GenericVisualizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.events, cls.snapshots = VIS.load_source_bundle(CAMPAIGN)
        cls.campaign = cls.source["campaign"]
        cls.compiled = VIS.compile_visual_frames(
            cls.campaign, cls.source["initial"], cls.events, cls.snapshots
        )
        cls.frames = cls.compiled["campaigns"][0]["frames"]
        cls.by_id = {frame["id"]: frame for frame in cls.frames}

    def test_offline_compile_matches_recorded_generic_frames(self):
        saved = json.loads((CAMPAIGN / "visual-frames-generic.json").read_text())
        saved_frames = saved["campaigns"][0]["frames"]
        self.assertEqual(self.frames, saved_frames)

    def test_incremental_compile_matches_offline_frame_sequence(self):
        compiler = VIS.VisualFrameCompiler(
            self.campaign["id"], self.campaign["title"], self.campaign["filename"],
            self.source["initial"]["revision"], self.source["initial"]["code"], self.snapshots,
            self.source["initial"].get("dependencies", []),
        )
        emitted = [compiler.consume(event) for event in self.events]
        self.assertEqual([f for f in emitted if f is not None], self.frames)

    def test_preview_and_rejection_preserve_authoritative_code_and_revision(self):
        initial = self.by_id["p14-start"]
        age_preview = self.by_id["p14-m2-preview"]
        age_commit = self.by_id["p14-m2-commit"]
        rejected = self.by_id["p14-m3-first-reject"]
        reset = self.by_id["p14-reset"]
        self.assertEqual(age_preview["revision"], 3)
        self.assertIn("PERSON_AGE(1) = 42", age_preview["code"])
        self.assertEqual(age_commit["revision"], 4)
        self.assertIn("PERSON_AGE(1) = 55", age_commit["code"])
        self.assertEqual(rejected["revision"], reset["revision"])
        self.assertEqual(rejected["code"], reset["code"])
        self.assertIn("FUNCTION IS_ADULT", self.by_id["p14-m3-commit"]["code"])

    def test_runtime_observation_stays_visible_with_revision_provenance(self):
        self.assertEqual(self.by_id["p14-m1-commit"]["observation_freshness"], "historical")
        self.assertEqual(self.by_id["p14-m2-commit"]["observation"]["revision"], 3)
        self.assertEqual(self.by_id["p14-m3-check"]["observation_freshness"], "current")
        self.assertTrue(self.by_id["p14-m3-check"]["observation"]["agreement"])

    def test_commit_requires_authoritative_snapshot_and_contiguous_sequence(self):
        compiler = VIS.VisualFrameCompiler("x", "X", "X.bas", 1, "", {2:"new"})
        initial = {"event_id":"e1","event_type":"initial","presentation_sequence":1,"revision":1,"provenance":"host"}
        compiler.consume(initial)
        with self.assertRaises(VIS.PresentationError):
            compiler.consume({"event_id":"e3","event_type":"commit","presentation_sequence":3,"revision":2,"provenance":"host"})
        with self.assertRaises(VIS.PresentationError):
            compiler.consume({"event_id":"e2","event_type":"commit","presentation_sequence":2,"revision":3,"provenance":"host"})

    def test_repeated_event_id_does_not_duplicate_commit(self):
        compiler = VIS.VisualFrameCompiler("x", "X", "X.bas", 1, "old", {2:"new"})
        event = {"event_id":"seed","event_type":"initial","presentation_sequence":1,"revision":1,"provenance":"host"}
        compiler.consume(event)
        self.assertIsNone(compiler.consume(event))
        commit = {"event_id":"commit","event_type":"commit","presentation_sequence":2,"revision":2,"provenance":"gateway"}
        compiler.consume(commit)
        self.assertEqual(compiler.revision, 2)
        self.assertEqual(len(compiler.frames), 2)

    def test_agent_mission_status_is_separate_from_committed_seed_and_code(self):
        compiler=VIS.VisualFrameCompiler("pi","Pi","P.bas",4,"seed code",{5:"committed code"})
        initial=compiler.consume({"event_id":"seed","event_type":"initial","revision":4,"provenance":"host",
            "mission_status":"Agent mission pending · committed seed revision 4"})
        self.assertEqual(initial["state"],"baseline")
        self.assertEqual(initial["mission_status"],"Agent mission pending · committed seed revision 4")
        denied=compiler.consume({"event_id":"reject","event_type":"rejection","revision":4,"provenance":"gateway"})
        self.assertEqual(denied["code"],"seed code")
        self.assertEqual(denied["mission_status"],initial["mission_status"])
        final=compiler.consume({"event_id":"outcome","event_type":"mission_status","revision":4,"provenance":"host",
            "mission_status":"Agent mission failed · no agent commit · revision 4 · timed out"})
        self.assertEqual(final["state"],"status")
        self.assertEqual(final["code"],"seed code")
        self.assertIn("failed",final["mission_status"])

    def test_exact_semantic_spans_are_supported_without_guessing_positions(self):
        compiler = VIS.VisualFrameCompiler("x", "X", "X.bas", 1, "X = 3", {})
        event = {"event_id":"e","event_type":"initial","revision":1,"provenance":"workspace",
                 "focus":{"handles":["stmt.handle"],"mapping":"exact_semantic_span",
                          "spans":{"ranges":[{"start_line":1,"start_column":4,"end_line":1,"end_column":5,"role":"literal"}]}}}
        frame = compiler.consume(event)
        self.assertEqual(frame["focus"]["spans"]["ranges"][0]["role"], "literal")

    def test_live_hub_deduplicates_frames_and_reports_gaps(self):
        hub = VIS.LiveEventHub(retention=2)
        self.assertTrue(hub.publish({"id":"a"}))
        self.assertFalse(hub.publish({"id":"a"}))
        hub.publish({"id":"b"})
        self.assertEqual([frame["id"] for _,frame in hub.after(1)[0]], ["b"])
        hub.publish({"id":"c"})
        with self.assertRaises(VIS.PresentationError):hub.after(0)

    def test_http_viewer_is_loopback_read_only_and_streams_frames(self):
        hub = VIS.LiveEventHub()
        server = VIS.ReadOnlyVisualServer("<html>viewer</html>", hub, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        try:
            with urlopen(server.url + "health", timeout=2) as response:
                health=json.loads(response.read())
            self.assertEqual(server.server.server_address[0], "127.0.0.1")
            self.assertTrue(health["read_only"])
            hub.publish({"id":"frame-1","revision":1});hub.finish()
            with urlopen(server.url + "events", timeout=2) as response:
                lines=[]
                for raw in response:
                    lines.append(raw.decode())
                    if "data: complete" in lines[-1]:break
                body="".join(lines)
            self.assertIn("event: frame", body)
            self.assertIn('"id":"frame-1"', body)
            self.assertIn("event: complete", body)
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(server.url + "events", data=b"{}", method="POST"), timeout=2)
            error.exception.close()
            self.assertEqual(error.exception.code, 405)
        finally:
            server.shutdown();thread.join(timeout=2)

    def test_interrupted_stream_emits_error_event(self):
        hub=VIS.LiveEventHub();hub.fail("test interruption")
        server=VIS.ReadOnlyVisualServer("<html></html>",hub,0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with urlopen(server.url+"events",timeout=2) as response:
                lines=[]
                for raw in response:
                    lines.append(raw.decode())
                    if "test interruption" in lines[-1]:break
                body="".join(lines)
            self.assertIn("event: stream-error",body)
            self.assertIn("test interruption",body)
        finally:
            server.shutdown();thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
