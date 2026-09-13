import unittest
import tempfile
import os
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch, MagicMock

# Import the functions from the module being tested
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import compaction_effect_check


class TestCompactionEffectCheck(unittest.TestCase):
    
    def setUp(self):
        # Create temporary directory and files for testing
        self.temp_dir = tempfile.mkdtemp()
        self.temp_db = os.path.join(self.temp_dir, "test.db")
        self.temp_state = os.path.join(self.temp_dir, "state.json")
        
        # Create a test database with sample data
        conn = sqlite3.connect(self.temp_db)
        cursor = conn.cursor()
        
        # Create the table
        cursor.execute("""
            CREATE TABLE session_model_usage (
                model TEXT,
                input_tokens INTEGER,
                cache_read_tokens INTEGER,
                estimated_cost_usd REAL,
                api_call_count INTEGER,
                last_seen TEXT
            )
        """)
        
        # Insert test data
        test_data = [
            ("glm-5.3-flash", 1000, 3000, 0.5, 10, "1609459200.0"),  # Within range
            ("other-model", 2000, 1000, 1.0, 20, "1609459200.0"),     # Within range
            ("glm-5.3-flash", 500, 1500, 0.25, 5, "1609372800.0"),    # Outside range (too early)
            ("another-model", 800, 2400, 0.4, 8, "1609632000.0"),     # Outside range (too late)
        ]
        
        cursor.executemany(
            "INSERT INTO session_model_usage VALUES (?, ?, ?, ?, ?, ?)",
            test_data
        )
        
        conn.commit()
        conn.close()
    
    def tearDown(self):
        # Clean up temp files
        for file in [self.temp_db, self.temp_state]:
            if os.path.exists(file):
                os.remove(file)
        os.rmdir(self.temp_dir)
    
    def test_metrics_calculation(self):
        # Temporarily change the DB_PATH to use the test database
        original_db_path = compaction_effect_check.DB_PATH
        compaction_effect_check.DB_PATH = self.temp_db
        
        try:
            # Test metrics calculation with specific time range
            start_time = 1609459200.0  # Jan 1, 2021
            end_time = 1609545600.0    # Jan 2, 2021 (24 hours later)
            
            result = compaction_effect_check.metrics(start_time, end_time)
            
            # Based on the test data, only the first two records should be included:
            # 1. ("glm-5.3-flash", 1000, 3000, 0.5, 10, "1609459200.0")
            # 2. ("other-model", 2000, 1000, 1.0, 20, "1609459200.0")
            #
            # So:
            # - Total cost: 0.5 + 1.0 = 1.5
            # - Compaction cost (glm-5.3-flash only): 0.5
            # - Compaction calls (glm-5.3-flash only): 10
            # - Days: (1609545600.0 - 1609459200.0) / 86400 = 1.0
            # - Total input: 1000 + 2000 = 3000
            # - Total cache: 3000 + 1000 = 4000
            # - Cache ratio: 4000 / 3000 = 1.333...
            
            days = (end_time - start_time) / 86400  # 1 day
            
            self.assertEqual(result["cost_per_day"], 1.5 / days)  # 1.5
            self.assertEqual(result["compaction_cost_per_day"], 0.5 / days)  # 0.5
            self.assertEqual(result["compaction_calls"], 10)  # Only glm-5.3-flash calls
            self.assertAlmostEqual(result["cache_ratio"], 4000 / 3000, places=2)  # ~1.33
        finally:
            # Restore original DB_PATH
            compaction_effect_check.DB_PATH = original_db_path
    
    @patch('compaction_effect_check.time.time')
    @patch('compaction_effect_check.metrics')
    def test_main_with_existing_state_reported(self, mock_metrics, mock_time):
        # Temporarily change STATE_FILE to use the temp file
        original_state_file = compaction_effect_check.STATE_FILE
        compaction_effect_check.STATE_FILE = self.temp_state
        
        try:
            # Create a state file with reported=True
            initial_state = {
                "change_ts": 1609459200.0,
                "observe_until": 1609372800.0,  # Past observation period
                "baseline": {"cost_per_day": 2.0},
                "reported": True  # Already reported
            }
            with open(self.temp_state, 'w') as f:
                json.dump(initial_state, f)
            
            # Set up mocks
            mock_time.return_value = 1609545600.0
            
            result = compaction_effect_check.main()
            
            # Should return early without further processing
            self.assertEqual(result, 0)
            # metrics should not be called since it's already reported
            mock_metrics.assert_not_called()
        finally:
            # Restore original STATE_FILE
            compaction_effect_check.STATE_FILE = original_state_file
    
    @patch('compaction_effect_check.time.time')
    @patch('compaction_effect_check.metrics')
    def test_main_observation_period_not_over(self, mock_metrics, mock_time):
        # Temporarily change STATE_FILE to use the temp file
        original_state_file = compaction_effect_check.STATE_FILE
        compaction_effect_check.STATE_FILE = self.temp_state
        
        try:
            # Create a state file with reported=False and future observe_until
            initial_state = {
                "change_ts": 1609459200.0,
                "observe_until": 1609632000.0,  # Future time
                "baseline": {"cost_per_day": 2.0},
                "reported": False
            }
            with open(self.temp_state, 'w') as f:
                json.dump(initial_state, f)
            
            # Set up mocks
            mock_time.return_value = 1609545600.0  # During observation period
            
            result = compaction_effect_check.main()
            
            # Should return early without reporting
            self.assertEqual(result, 0)
            # metrics should not be called since observation period isn't over
            mock_metrics.assert_not_called()
        finally:
            # Restore original STATE_FILE
            compaction_effect_check.STATE_FILE = original_state_file


if __name__ == '__main__':
    unittest.main()