import unittest
import os
import sys
from datetime import datetime, timezone
import sqlite3
import tempfile
from unittest.mock import patch, mock_open

# Add the script directory to the path so it can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import thinking_layer_cost


class TestThinkingLayerCost(unittest.TestCase):
    
    def test_constants_exist_and_are_correct_types(self):
        """Test that the expected constants exist and have correct types"""
        self.assertIsInstance(thinking_layer_cost.THINKING, set)
        self.assertIsInstance(thinking_layer_cost.DAY_CAP_USD, (int, float))
        self.assertIsInstance(thinking_layer_cost.THINK_CAP_USD, (int, float))
        
        # Check specific values
        self.assertIn("minimax/minimax-m3", thinking_layer_cost.THINKING)
        self.assertGreaterEqual(thinking_layer_cost.DAY_CAP_USD, 0)
        self.assertGreaterEqual(thinking_layer_cost.THINK_CAP_USD, 0)
        self.assertLessEqual(thinking_layer_cost.THINK_CAP_USD, thinking_layer_cost.DAY_CAP_USD)

    @patch('builtins.open', new_callable=mock_open, read_data='TEST_VAR=test_value_from_file\nOTHER_VAR=other_value\n')
    @patch('os.path.expanduser', return_value='/fake/path/.env')
    def test_env_function_reads_from_file(self, mock_expanduser, mock_file):
        """Test the env function with a key that exists in the .env file"""
        result = thinking_layer_cost.env('TEST_VAR')
        self.assertEqual(result, 'test_value_from_file')

    @patch('builtins.open', side_effect=OSError())
    def test_env_function_returns_default_when_file_missing(self, mock_file):
        """Test the env function returns default when file doesn't exist"""
        result = thinking_layer_cost.env('NONEXISTENT_VAR', 'default_value')
        self.assertEqual(result, 'default_value')


class TestWatchList(unittest.TestCase):
    """The watch list is optional data: missing or broken file means 'nothing watched'."""

    def test_load_watch_returns_empty_when_file_missing(self):
        with patch.object(thinking_layer_cost, 'WATCH_FILE', '/nonexistent/watch.json'):
            self.assertEqual(thinking_layer_cost.load_watch(), {})

    def test_load_watch_reads_json_and_normalises_pairs(self):
        payload = '{"model/x": ["2026-09-22", "why"], "model/y": ["2026-09-23", "why too"]}'
        with patch('builtins.open', mock_open(read_data=payload)):
            got = thinking_layer_cost.load_watch()
        self.assertEqual(set(got), {"model/x", "model/y"})
        self.assertEqual(got["model/x"], ("2026-09-22", "why"))

    def test_load_watch_survives_broken_payload(self):
        with patch('builtins.open', mock_open(read_data='{not json')):
            self.assertEqual(thinking_layer_cost.load_watch(), {})

    def test_watch_report_prunes_old_and_future_entries(self):
        today = datetime.now(timezone.utc).date().isoformat()
        watch = {"model/old": ("2020-01-01", "stale"), "model/new": (today, "fresh")}
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "state.db")
            con = sqlite3.connect(db)
            con.execute(
                "create table session_model_usage (model text, api_call_count int, input_tokens int,"
                " cache_read_tokens int, output_tokens int, estimated_cost_usd real)"
            )
            con.execute(
                "insert into session_model_usage values ('model/new', 2, 1000, 9000, 50, 0.01)"
            )
            con.commit()
            con.close()
            with patch.object(thinking_layer_cost, 'DB', db):
                lines = thinking_layer_cost.watch_report(today, watch=watch)
        joined = "\n".join(lines)
        self.assertIn("new", joined)
        self.assertNotIn("old", joined)
        self.assertIn("day 1/", joined)


if __name__ == '__main__':
    unittest.main()