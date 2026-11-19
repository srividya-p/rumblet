"""Parenthesized expressions and empty sequence evaluation."""

import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

from rumblet.engine import evaluate
from rumblet.errors import StaticError
from rumblet.sequence import Sequence, print_sequence

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests/queries/slice06/cases.json").read_text())["cases"]


class ParenthesizedExpressionTests(unittest.TestCase):
    def test_evaluate(self):
        for case in CASES:
            with self.subTest(expression=case["expr"]):
                if case["exit_code"]:
                    with self.assertRaises(StaticError):
                        evaluate(case["expr"])
                    continue
                result = evaluate(case["expr"])
                if case["stdout"] == "()\n":
                    self.assertEqual(result, Sequence([]))
                else:
                    self.assertEqual(len(result), len(case["stdout"].splitlines()))
                output = io.StringIO()
                print_sequence(result, file=output)
                self.assertEqual(output.getvalue(), case["stdout"])

    def test_cli(self):
        for case in CASES:
            with self.subTest(expression=case["expr"]):
                result = subprocess.run(
                    [sys.executable, "-m", "rumblet", "run", "--expr", case["expr"]],
                    cwd=ROOT, capture_output=True, text=True, check=False,
                )
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (case["exit_code"], case["stdout"], case["stderr"]))
