"""No-network tests for Claude Pro usage ledger; run python -m unittest."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import claude_usage_stats as m


class UsageTest(unittest.TestCase):
    def test_error_classifier(self):
        for msg in ["Rate limit reached, resets at 12:00", "LIMIT_COOLDOWN", "usage limit"]:
            self.assertEqual(m.error_kind(msg),"limit")
        self.assertEqual(m.error_kind("OAuth session expired"),"auth")
        self.assertEqual(m.error_kind("timed out"),"timeout")
        self.assertEqual(m.error_kind("file does not exist"),"failed")

    def test_tokens_and_no_fake_quota(self):
        vals=m.usage_from_event({"usage":{"input_tokens":25,"output_tokens":13,"foo":52}})
        self.assertEqual(vals,{"input_tokens":25,"output_tokens":13})
        self.assertIsNone(m._summarize([])["subscription_remaining"])

    def test_record_counts_and_private_files(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"jobs").mkdir()
            with patch.object(m,"ROOT",root),patch.object(m,"HISTORY",root/"usage_history.jsonl"),patch.object(m,"SUMMARY",root/"usage.json"):
                m.record(status="done",pages=3,rows=43,seconds=15.4,tokens={"output_tokens":400})
                m.record(status="failed",pages=2,error="usage limit exceeded",seconds=0.2)
                data=json.loads((root/"usage.json").read_text())
                self.assertEqual(data["done"],1)
                self.assertEqual(data["failed"],1)
                self.assertEqual(data["pages_24h"],3)
                self.assertEqual(data["rows_done"],43)
                self.assertEqual(data["last_error_kind"],"limit")
                self.assertIsNone(data["subscription_remaining"])
                self.assertEqual(len((root/"usage_history.jsonl").read_text().splitlines()),2)
                self.assertNotIn("project", (root/"usage.json").read_text())
                m.heartbeat()
                self.assertGreater(json.loads((root/"heartbeat.json").read_text())["epoch"],0)


class HostLimitTest(unittest.TestCase):
    def test_rate_limit_stops_following_jobs_without_extra_claude_calls(self):
        import time,uuid
        from unittest.mock import Mock
        import claude_bridge_host as host
        with tempfile.TemporaryDirectory() as td:
            host.LIMIT_COOLDOWN_UNTIL=0
            with patch.object(host,"read_page",side_effect=RuntimeError("rate limit reached")) as reader, patch.object(host,"record") as metrics:
                for i in range(2):
                    doc_id=str(uuid.uuid4())
                    folder=Path(td)/doc_id
                    folder.mkdir()
                    host.process_job(folder,{"job_id":doc_id,"pages":1,"dzial":"hydraulika"})
                    result=json.loads((folder/"result.json").read_text())
                    self.assertEqual(result["error_code"],"limit")
                self.assertEqual(reader.call_count,1)
                self.assertGreater(host.LIMIT_COOLDOWN_UNTIL,time.monotonic())
                self.assertEqual(metrics.call_count,2)
                self.assertEqual(metrics.call_args.kwargs["status"],"failed")
            host.LIMIT_COOLDOWN_UNTIL=0


if __name__=="__main__":unittest.main()
