import unittest
import os
import json
import tempfile
from datetime import datetime
from unittest.mock import patch, mock_open

# Import the functions from ecosystem_map module
import sys
sys.path.insert(0, '..')  # Add parent directory to path to import ecosystem_map
from ecosystem_map import deliver_label, fmt_last, build_map, diff_report


class TestEcosystemMap(unittest.TestCase):

    def setUp(self):
        """Setup test fixtures before each test method."""
        self.sample_job = {
            "id": "abc123def456",
            "name": "test_job",
            "state": "scheduled",
            "last_run_at": "2023-10-01T10:00:00Z",
            "last_status": "ok",
            "failure_streak": 0,
            "schedule_display": "daily",
            "model": "gpt-4",
            "deliver": "origin",
            "origin": {
                "chat_id": "100000000"
            }
        }

    def test_deliver_label_local(self):
        """Test deliver_label with local delivery."""
        job = {"deliver": "local"}
        result = deliver_label(job)
        self.assertEqual(result, "local")

    @patch.dict(os.environ, {"HERMES_OPERATOR_CHAT": "100000000"})
    def test_deliver_label_direct_message(self):
        """Test deliver_label with direct message delivery."""
        job = {
            "deliver": "origin",
            "origin": {"chat_id": "100000000"}
        }
        result = deliver_label(job)
        self.assertIn("📩", result)

    def test_fmt_last_ok_status(self):
        """Test fmt_last with ok status."""
        job = {
            "last_run_at": "2023-10-01T10:00:00Z",
            "last_status": "ok",
            "failure_streak": 0
        }
        result = fmt_last(job)
        self.assertIn("🟢", result)

    def test_fmt_last_error_status(self):
        """Test fmt_last with error status."""
        job = {
            "last_run_at": "2023-10-01T10:00:00Z",
            "last_status": "error",
            "failure_streak": 3
        }
        result = fmt_last(job)
        self.assertIn("🔴", result)

    def test_fmt_last_never_run(self):
        """Test fmt_last for job that never ran."""
        job = {
            "last_run_at": None,
            "last_status": None,
            "failure_streak": 0
        }
        result = fmt_last(job)
        self.assertIn("not run", result)

    def test_build_map_basic(self):
        """Test build_map with basic input."""
        jobs = [self.sample_job]
        profiles = ["default", "profile1"]
        channels_idx = {}

        result = build_map(jobs, profiles, channels_idx)
        
        # Check that the result contains expected elements
        self.assertIn("Agent Ecosystem Map", result)
        self.assertIn("test_job", result)
        self.assertIn("default", result)
        self.assertIn("profile1", result)

    def test_diff_report_new_job(self):
        """Test diff_report with a new job."""
        jobs = [self.sample_job]
        old_state = {"jobs": {}}
        
        changes = diff_report(old_state, jobs)
        self.assertTrue(any("new cron" in change for change in changes))

    def test_diff_report_removed_job(self):
        """Test diff_report with a removed job."""
        old_job = {
            "id": "old123",
            "name": "old_job",
            "state": "scheduled"
        }
        old_state = {"jobs": {"old123": old_job}}
        jobs = []
        
        changes = diff_report(old_state, jobs)
        self.assertTrue(any("removed cron" in change for change in changes))

    def test_diff_report_state_change(self):
        """Test diff_report with state change."""
        job = {
            "id": "abc123",
            "name": "test_job",
            "state": "paused"
        }
        old_job = {
            "id": "abc123",
            "name": "test_job",
            "state": "scheduled"
        }
        old_state = {"jobs": {"abc123": old_job}}
        jobs = [job]
        
        changes = diff_report(old_state, jobs)
        self.assertTrue(any("paused" in change for change in changes))


if __name__ == '__main__':
    unittest.main()