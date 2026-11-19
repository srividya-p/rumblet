"""Comma expressions and concatenation iterator lifecycle."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from rumblet.__main__ import main
from rumblet.engine import evaluate
from rumblet.errors import DynamicError, StaticError
from rumblet.runtime import CommaIterator, LiteralIterator
from rumblet.sequence import print_sequence
from rumblet.values import NumberValue

CASES = json.loads((Path(__file__).parent / "queries/slice08/cases.json").read_text())["cases"]


class CommaTests(unittest.TestCase):
    def test_query_cases(self):
        error_types = {"DynamicError": DynamicError, "StaticError": StaticError}
        for case in CASES:
            with self.subTest(expression=case["expr"]):
                expr = case["expr"]
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(["run", "--expr", expr])
                self.assertEqual((exit_code, stdout.getvalue(), stderr.getvalue()),
                                 (case["exit_code"], case["stdout"], case["stderr"]))
                if case["exit_code"]:
                    with self.assertRaises(error_types[case["error_type"]]):
                        evaluate(expr)
                else:
                    output = io.StringIO()
                    print_sequence(evaluate(expr), file=output)
                    self.assertEqual(output.getvalue(), case["stdout"])

    def test_reset_and_close_release_active_operand(self):
        first = LiteralIterator(NumberValue(1))
        second = LiteralIterator(NumberValue(2))
        iterator = CommaIterator((first, second))
        iterator.open()
        try:
            self.assertEqual(iterator.next(), NumberValue(1))
            with self.assertRaisesRegex(DynamicError, "iterator is not open"):
                second.next()
            iterator.reset()
            with self.assertRaisesRegex(DynamicError, "iterator is not open"):
                first.next()
            self.assertEqual(iterator.next(), NumberValue(1))
            self.assertEqual(iterator.next(), NumberValue(2))
        finally:
            iterator.close()
        with self.assertRaisesRegex(DynamicError, "iterator is not open"):
            second.next()
