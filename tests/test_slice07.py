"""Arithmetic precedence, operand validation, and CLI evaluation."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

from rumblet.engine import evaluate
from rumblet.errors import DynamicError, StaticError
from rumblet.runtime import ArithmeticIterator, LiteralIterator, RuntimeIterator
from rumblet.values import NumberValue

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests/queries/slice07/cases.json").read_text())["cases"]


class TwoNumbers(RuntimeIterator):
    def _restart(self):
        self._values = iter((NumberValue(1), NumberValue(2)))

    def _next(self):
        return next(self._values)


class ArithmeticTests(unittest.TestCase):
    def test_evaluate(self):
        error_types = {"DynamicError": DynamicError, "StaticError": StaticError}
        for case in CASES:
            with self.subTest(expression=case["expr"]):
                if case["exit_code"]:
                    with self.assertRaises(error_types[case["error_type"]]):
                        evaluate(case["expr"])
                    continue
                values = evaluate(case["expr"]).values
                self.assertEqual(values, [NumberValue(json.loads(case["stdout"]))])

    def test_cli(self):
        for case in CASES:
            with self.subTest(expression=case["expr"]):
                result = subprocess.run(
                    [sys.executable, "-m", "rumblet", "run", "--expr=" + case["expr"]],
                    cwd=ROOT, capture_output=True, text=True, check=False,
                )
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (case["exit_code"], case["stdout"], case["stderr"]))

    def test_rejects_multiple_numbers_and_closes_operand(self):
        child = TwoNumbers()
        iterator = ArithmeticIterator("+", (child,))
        iterator.open()
        try:
            with self.assertRaisesRegex(DynamicError, "exactly one number"):
                iterator.next()
            with self.assertRaisesRegex(DynamicError, "iterator is not open"):
                child.next()
        finally:
            iterator.close()

    def test_reset_replays_result(self):
        iterator = ArithmeticIterator("-", (LiteralIterator(NumberValue(3)),))
        iterator.open()
        try:
            self.assertEqual(iterator.next(), NumberValue(-3))
            with self.assertRaises(StopIteration):
                iterator.next()
            iterator.reset()
            self.assertEqual(iterator.next(), NumberValue(-3))
        finally:
            iterator.close()
