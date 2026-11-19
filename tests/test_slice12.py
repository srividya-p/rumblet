"""Value comparison query cases and iterator lifecycle."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from rumblet.__main__ import main
from rumblet.runtime import ComparisonIterator, LiteralIterator
from rumblet.values import BooleanValue, NumberValue

CASES = json.loads((Path(__file__).parent / "queries/slice12/cases.json").read_text())["cases"]


class ValueComparisonTests(unittest.TestCase):
    def test_query_cases(self):
        for case in CASES:
            with self.subTest(expression=case["expr"]):
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(["run", "--expr", case["expr"]])
                self.assertEqual(
                    (exit_code, stdout.getvalue(), stderr.getvalue()),
                    (case.get("exit_code", 0), case["stdout"], case.get("stderr", "")),
                )

    def test_iterator_emits_one_boolean_per_open_or_reset(self):
        left = LiteralIterator(NumberValue(1))
        right = LiteralIterator(NumberValue(2))
        iterator = ComparisonIterator("lt", left, right)
        iterator.open()
        try:
            self.assertEqual(iterator.next(), BooleanValue(True))
            with self.assertRaises(StopIteration):
                iterator.next()
            iterator.reset()
            self.assertEqual(iterator.next(), BooleanValue(True))
        finally:
            iterator.close()
