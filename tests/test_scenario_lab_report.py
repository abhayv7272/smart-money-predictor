import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from scenario_lab_report import (
    load_scenario_lab_data,
    render_scenario_lab_html,
    render_scenario_lab_markdown,
)


class ScenarioLabReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_scenario_lab_data(
            os.path.join(ROOT, "nifty-scenario-lab-github.zip")
        )

    def test_archive_snapshot_is_added_to_both_report_formats(self):
        self.assertIsNotNone(self.bundle)
        html = render_scenario_lab_html(self.bundle, "2026-10-01")
        markdown = render_scenario_lab_markdown(self.bundle, "2026-10-01")

        self.assertIn("NIFTY MARKET SCENARIO LAB", html)
        self.assertIn("65.8%", html)
        self.assertIn("Q5/5", html)
        self.assertIn("srcdoc=", html)
        self.assertIn("NIFTY Market Scenario Lab", markdown)
        self.assertIn("Slow Bleed", markdown)
        self.assertIn("83.8%", markdown)

    def test_accuracy_table_uses_majority_baseline_for_dip_risk(self):
        markdown = render_scenario_lab_markdown(self.bundle, "2026-10-01")
        self.assertIn(
            "| 3M dip greater than 5% | 64.1% | 65.4% | 0.570 |",
            markdown,
        )


if __name__ == "__main__":
    unittest.main()
