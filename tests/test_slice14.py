"""Conditional query cases and selected branch lifecycle."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from rumblet.__main__ import main
from rumblet.errors import DynamicError
from rumblet.runtime import CommaIterator, IfIterator, LiteralIterator
from rumblet.values import BooleanValue, NumberValue

CASES = json.loads((Path(__file__).parent / "queries/slice14/cases.json").read_text())["cases"]


class ConditionalTests(unittest.TestCase):
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

    def test_reset_rewinds_partially_consumed_branch_and_close_releases_it(self):
        first, second = NumberValue(1), NumberValue(2)
        selected = CommaIterator((LiteralIterator(first), LiteralIterator(second)))
        iterator = IfIterator(
            LiteralIterator(BooleanValue(True)), selected, LiteralIterator(NumberValue(3)),
        )
        iterator.open()
        try:
            self.assertEqual(iterator.next(), first)
            iterator.reset()
            self.assertEqual(iterator.next(), first)
            self.assertEqual(iterator.next(), second)
        finally:
            iterator.close()
        with self.assertRaisesRegex(DynamicError, "iterator is not open"):
            selected.next()
