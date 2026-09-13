import unittest
from datetime import datetime
import sys
from pathlib import Path

# Add the script directory to path to import research_scout
sys.path.insert(0, str(Path(__file__).parent.parent))

import research_scout


class TestThemeScores(unittest.TestCase):
    def test_theme_detection(self):
        title = "Agent Harness for Large Language Models"
        abstract = "We present a new agent memory system for LLMs."
        
        scores, total = research_scout.theme_scores(title, abstract)
        
        # Should detect "harness" in title (weight 3) and "memory" in abstract (weight 1)
        self.assertIn("harness", scores)
        self.assertEqual(scores["harness"], 3)  # Title hit
        self.assertIn("memory", scores)
        self.assertEqual(scores["memory"], 1)  # Abstract hit
        
        # Total should be at least 4 (3+1)
        self.assertGreaterEqual(total, 4)
    
    def test_no_matches(self):
        title = "Random Computer Science Paper"
        abstract = "This paper is about unrelated topics."
        
        scores, total = research_scout.theme_scores(title, abstract)
        
        # No themes should match
        self.assertEqual(len(scores), 0)
        self.assertEqual(total, 0)
    
    def test_case_insensitive(self):
        title = "AGENT MEMORY SYSTEM"
        abstract = "Tool Use in AI"
        
        scores, total = research_scout.theme_scores(title, abstract)
        
        self.assertIn("memory", scores)
        self.assertIn("harness", scores)  # tool use
        self.assertGreater(total, 0)


class TestConstants(unittest.TestCase):
    def test_constants_defined(self):
        # Check that required constants are defined
        self.assertIsInstance(research_scout.WINDOW_DAYS, int)
        self.assertIsInstance(research_scout.CACHE_MINUTES, int)
        self.assertIsInstance(research_scout.MAX_ITEMS, int)
        self.assertGreaterEqual(research_scout.WINDOW_DAYS, 1)
        self.assertGreaterEqual(research_scout.CACHE_MINUTES, 1)
        self.assertGreaterEqual(research_scout.MAX_ITEMS, 1)
    
    def test_themes_defined(self):
        # Check that themes dictionary exists and has content
        self.assertIsInstance(research_scout.THEMES, dict)
        self.assertGreater(len(research_scout.THEMES), 0)
        self.assertIn("harness", research_scout.THEMES)
        self.assertIn("evals", research_scout.THEMES)


if __name__ == '__main__':
    unittest.main()