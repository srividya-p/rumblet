"""Single-clause for queries and return iterator resets."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from rumblet.__main__ import main
from rumblet.errors import DynamicError
from rumblet.runtime import CommaIterator, ForIterator, LiteralIterator, VariableIterator
from rumblet.sequence import Sequence
from rumblet.values import NumberValue

CASES = json.loads((Path(__file__).parent / "queries/slice16/cases.json").read_text())["cases"]


class ForTests(unittest.TestCase):
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

    def test_return_plan_resets_for_every_binding(self):
        resets = []

        class RecordingVariable(VariableIterator):
            def reset(self, context=None, bindings=None):
                super().reset(context, bindings)
                resets.append(self.context.lookup("x"))

        first, second = NumberValue(1), NumberValue(2)
        source = CommaIterator((LiteralIterator(first), LiteralIterator(second)))
        body = RecordingVariable("x")
        iterator = ForIterator("x", source, body)
        iterator.open()
        try:
            self.assertEqual(iterator.next(), first)
            self.assertEqual(iterator.next(), second)
            self.assertEqual(resets, [Sequence([first]), Sequence([second])])
            iterator.reset()
            for child in (source, body):
                with self.assertRaisesRegex(DynamicError, "iterator is not open"):
                    child.next()
            self.assertEqual(iterator.next(), first)
        finally:
            iterator.close()
        for child in (source, body):
            with self.assertRaisesRegex(DynamicError, "iterator is not open"):
                child.next()
