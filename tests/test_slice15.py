"""Variable reference queries and iterator lifecycle."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from rumblet.__main__ import main
from rumblet.context import DynamicContext
from rumblet.engine import _build_iterator
from rumblet.parser import parse
from rumblet.runtime import VariableIterator
from rumblet.sequence import Sequence
from rumblet.values import NumberValue

CASES = json.loads((Path(__file__).parent / "queries/slice15/cases.json").read_text())["cases"]


class VariableReferenceTests(unittest.TestCase):
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

    def test_reset_reads_replaced_binding(self):
        first, second = NumberValue(1), NumberValue(2)
        iterator = VariableIterator("x")
        iterator.open(bindings={"x": Sequence([first, first])})
        try:
            self.assertEqual(iterator.next(), first)
            iterator.reset(bindings={"x": Sequence([second])})
            self.assertEqual(iterator.next(), second)
            with self.assertRaises(StopIteration):
                iterator.next()
        finally:
            iterator.close()

    def test_let_reset_rewinds_return_and_preserves_caller_binding(self):
        outer = Sequence([NumberValue(9)])
        context = DynamicContext({"x": outer})
        iterator = _build_iterator(parse("let $x := (1, 2) return $x"))
        iterator.open(context)
        try:
            self.assertEqual(iterator.next(), NumberValue(1))
            self.assertEqual(context.lookup("x"), outer)
            iterator.reset()
            self.assertEqual(iterator.next(), NumberValue(1))
            self.assertEqual(iterator.next(), NumberValue(2))
            with self.assertRaises(StopIteration):
                iterator.next()
        finally:
            iterator.close()
