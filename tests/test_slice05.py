"""Literal parsing, singleton evaluation, and CLI output."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

from rumblet.engine import evaluate
from rumblet.errors import StaticError
from rumblet.parser import LiteralExpr, parse

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests/queries/slice05/cases.json").read_text())["cases"]


class LiteralTests(unittest.TestCase):
    def test_parse_and_evaluate(self):
        for case in CASES:
            with self.subTest(expression=case["expr"]):
                if case["exit_code"]:
                    with self.assertRaises(StaticError):
                        evaluate(case["expr"])
                    continue
                literal = parse(case["expr"])
                self.assertIsInstance(literal, LiteralExpr)
                values = evaluate(case["expr"]).values
                self.assertEqual(values, [literal.value])
                self.assertEqual(values[0].kind, case["kind"])
                self.assertEqual(values[0].value, json.loads(case["stdout"]))

    def test_cli(self):
        for case in CASES:
            with self.subTest(expression=case["expr"]):
                result = subprocess.run(
                    [sys.executable, "-m", "rumblet", "run", "--expr=" + case["expr"]],
                    cwd=ROOT, capture_output=True, text=True, check=False,
                )
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (case["exit_code"], case["stdout"], case["stderr"]))
