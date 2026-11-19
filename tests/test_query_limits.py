"""CLI regression cases for evaluation and serialization limits."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests/queries/query_limits/cases.json").read_text())["cases"]


class QueryLimitTests(unittest.TestCase):
    def test_query_cases(self):
        for index, case in enumerate(CASES, start=1):
            with self.subTest(case=index):
                result = subprocess.run(
                    [sys.executable, "-m", "rumblet", "run", "--expr", case["expr"]],
                    cwd=ROOT,
                    env={**os.environ, "PYTHONINTMAXSTRDIGITS": "4300"},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(
                    (result.returncode, result.stdout, result.stderr),
                    (case["exit_code"], case["stdout"], case["stderr"]),
                )
