"""Initialization checks; fixtures are also the executable query examples."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests/queries/slice00/cases.json").read_text())["cases"]


class InitializationTests(unittest.TestCase):
    def test_query_files_match_cli(self):
        for case in CASES:
            with self.subTest(expression=case["expr"]):
                result = subprocess.run(
                    [sys.executable, "-m", "rumblet", "run", "--expr", case["expr"]],
                    cwd=ROOT, capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, case["exit_code"])
                self.assertEqual(result.stdout, case["stdout"])
                self.assertEqual(result.stderr, case["stderr"])

    def test_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "rumblet", "--help"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("run", result.stdout)
