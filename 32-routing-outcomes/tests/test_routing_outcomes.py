import unittest
import json
import tempfile
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Import the main module
import sys
sys.path.insert(0, '.')
from routing_outcomes import load_jobs, main


class TestRoutingOutcomes(unittest.TestCase):

    def setUp(self):
        # Create temporary files for testing
        self.temp_dir = tempfile.mkdtemp()
        self.jobs_file = Path(self.temp_dir) / "jobs.json"
        self.audit_file = Path(self.temp_dir) / "usage_audit.jsonl"
        
        # Set environment variables to use temp files
        os.environ["AGENT_HOME"] = self.temp_dir
        
    def tearDown(self):
        # Clean up temp files
        del os.environ["AGENT_HOME"]
        
    def test_load_jobs_with_list(self):
        """Test loading jobs when data is a list"""
        jobs_data = [
            {"id": "job1", "name": "test_job", "model": "gpt-4"},
            {"id": "job2", "name": "another_job", "model": "claude"}
        ]
        with open(self.jobs_file, 'w') as f:
            json.dump(jobs_data, f)
            
        result = load_jobs(self.jobs_file)
        self.assertEqual(len(result), 2)
        self.assertEqual(result["job1"]["name"], "test_job")
        
    def test_load_jobs_with_dict(self):
        """Test loading jobs when data has jobs key"""
        jobs_data = {
            "jobs": [
                {"id": "job1", "name": "test_job", "model": "gpt-4"}
            ]
        }
        with open(self.jobs_file, 'w') as f:
            json.dump(jobs_data, f)
            
        result = load_jobs(self.jobs_file)
        self.assertEqual(len(result), 1)
        self.assertEqual(result["job1"]["name"], "test_job")
        
    def test_main_empty_audit(self):
        """Test main with empty audit file"""
        with open(self.jobs_file, 'w') as f:
            json.dump([], f)
        with open(self.audit_file, 'w') as f:
            f.write("")
            
        # Capture stdout to verify output
        import io
        from contextlib import redirect_stdout
        
        f = io.StringIO()
        with redirect_stdout(f):
            result = main(self.audit_file, self.jobs_file)
        
        output = f.getvalue()
        self.assertIn("no audit data in window", output)
        self.assertEqual(result, 0)


if __name__ == '__main__':
    unittest.main()
