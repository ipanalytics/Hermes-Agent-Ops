import unittest
import tempfile
import os
import json
from datetime import datetime, timedelta
import sqlite3

# Import the functions under test
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# We'll mock the external dependencies
import ag_domain_scout


class TestAgDomainScout(unittest.TestCase):

    def setUp(self):
        # Create a temporary database for testing
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp()
        ag_domain_scout.DB = self.temp_db_path
        
        # Mock CLIENTS dictionary
        ag_domain_scout.CLIENTS = {
            "192.168.1.100": "TestDevice1",
            "192.168.1.101": "TestDevice2"
        }
        
        # Initialize database
        con = sqlite3.connect(ag_domain_scout.DB)
        ag_domain_scout.init_db(con)
        con.close()

    def tearDown(self):
        # Close and remove the temporary database
        os.close(self.temp_db_fd)
        os.unlink(self.temp_db_path)

    def test_parse_valid_json(self):
        # Test parsing valid querylog entries
        sample_log = '''{"IP":"192.168.1.100","QH":"example.com.","T":"2023-01-01T10:00:00Z","Result":{"IsFiltered":false}}
{"IP":"192.168.1.101","QH":"test.org.","T":"2023-01-01T10:01:00Z","Result":{"IsFiltered":true}}'''
        
        result = ag_domain_scout.parse(sample_log)
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], "192.168.1.100")  # IP
        self.assertEqual(result[0][1], "example.com")     # Domain
        self.assertEqual(result[0][2], "2023-01-01T10:00:00")  # Time
        self.assertFalse(result[0][3])  # Not blocked
        
        self.assertEqual(result[1][0], "192.168.1.101")  # IP
        self.assertEqual(result[1][1], "test.org")        # Domain
        self.assertTrue(result[1][3])  # Blocked

    def test_parse_invalid_json(self):
        # Test parsing invalid JSON
        sample_log = '''{"IP":"192.168.1.100","QH":"example.com.","T":"2023-01-01T10:00:00Z","Result":{"IsFiltered":false}}
invalid json line
{"IP":"192.168.1.101","QH":"test.org.","T":"2023-01-01T10:01:00Z","Result":{"IsFiltered":true}}'''
        
        result = ag_domain_scout.parse(sample_log)
        
        # Should only return the valid entries
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], "192.168.1.100")
        self.assertEqual(result[1][0], "192.168.1.101")

    def test_parse_empty_and_whitespace(self):
        # Test parsing with empty lines and whitespace
        sample_log = '''
{"IP":"192.168.1.100","QH":"example.com.","T":"2023-01-01T10:00:00Z","Result":{"IsFiltered":false}}

{"IP":"192.168.1.101","QH":"test.org.","T":"2023-01-01T10:01:00Z","Result":{"IsFiltered":true}}
   '''
        
        result = ag_domain_scout.parse(sample_log)
        
        self.assertEqual(len(result), 2)

    def test_report_cut_with_no_baseline(self):
        # Test report_cut when no baseline exists
        con = sqlite3.connect(ag_domain_scout.DB)
        ag_domain_scout.init_db(con)
        
        # Calculate expected cut date (7 days ago)
        expected_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
        result = ag_domain_scout.report_cut(con, 7)
        
        # Check that the result is approximately the expected date
        # (allow some variance due to timing)
        self.assertGreaterEqual(result, expected_date[:-4])  # Allow for minute-level differences
        
        con.close()

    def test_noise_filtering(self):
        # Test that noise patterns are properly detected
        noise_patterns = [
            "device.local",
            "service.internal",
            "something.arpa",
            "_service._tcp.local",
            "analytics.mixpanel.com",
            "tracking.amplitude.com"
        ]
        
        for pattern in noise_patterns:
            self.assertTrue(ag_domain_scout.NOISE.search(pattern), 
                           f"Pattern '{pattern}' should be detected as noise")

    def test_non_noise_domains(self):
        # Test that valid domains are not flagged as noise
        valid_domains = [
            "example.com",
            "google.com",
            "github.com",
            "valid.domain.org"
        ]
        
        for domain in valid_domains:
            self.assertIsNone(ag_domain_scout.NOISE.search(domain),
                             f"Valid domain '{domain}' should not be detected as noise")


if __name__ == '__main__':
    unittest.main()