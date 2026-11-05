import json
import tempfile
import unittest
from pathlib import Path

from tinyd_evidence.collector import export_bundle, read_jsonl


class EvidenceCollectorTests(unittest.TestCase):
    def test_exports_only_matching_trace_and_redacts_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "events.jsonl"
            records = [
                {"trace_id": "t-1", "event_type": "REQUEST", "timestamp": "2026-11-05T01:00:00Z",
                 "service": "gateway", "prompt": "hello", "api_key": "sk-live-secret"},
                {"trace_id": "t-1", "event_type": "SCHEDULED", "timestamp": "2026-11-05T01:00:01Z",
                 "service": "scheduler", "topic": "tinyd.requests"},
                {"trace_id": "t-1", "event_type": "EXECUTING", "timestamp": "2026-11-05T01:00:02Z",
                 "service": "worker", "worker_id": "w-1"},
                {"trace_id": "t-1", "event_type": "RESULT", "timestamp": "2026-11-05T01:00:03Z",
                 "service": "worker", "response": "done"},
                {"trace_id": "other", "event_type": "REQUEST", "timestamp": "2026-11-05T01:00:00Z",
                 "service": "gateway"}
            ]
            source.write_text("\n".join(json.dumps(x) for x in records), encoding="utf-8")
            out = root / "evidence"
            manifest = export_bundle(read_jsonl([source]), "t-1", out, zip_output=True)
            self.assertEqual(manifest["completeness"]["record_count"], 4)
            self.assertEqual(manifest["completeness"]["assessment"], "TRACE_PRESENT_REQUIRES_REVIEW")
            exported = (out / "prompt_response.log").read_text()
            self.assertNotIn("sk-live-secret", exported)
            self.assertTrue((root / "evidence.zip").exists())

    def test_missing_trace_is_not_fabricated(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "evidence"
            manifest = export_bundle([], "missing", out)
            self.assertEqual(manifest["completeness"]["assessment"], "NO_DATA")
            self.assertEqual(manifest["completeness"]["record_count"], 0)


if __name__ == "__main__":
    unittest.main()
