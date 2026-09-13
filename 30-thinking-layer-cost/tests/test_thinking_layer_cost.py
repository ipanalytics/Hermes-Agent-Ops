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


if __name__ == '__main__':
    unittest.main()