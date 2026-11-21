"""Full FLWOR queries, including nested scope isolation and resets."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from rumblet.__main__ import main
from rumblet.context import DynamicContext
from rumblet.engine import _build_iterator
from rumblet.errors import DynamicError
from rumblet.parser import parse
from rumblet.sequence import Sequence, print_sequence
from rumblet.values import NumberValue

CASES = json.loads((Path(__file__).parent / "queries/slice18/cases.json").read_text())["cases"]


class FlworTests(unittest.TestCase):
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

    def test_partial_reset_restarts_nested_return_without_leaking_bindings(self):
        case = next(case for case in CASES if case.get("name") == "nested_return")
        iterator = _build_iterator(parse(case["expr"]))
        first_binding = Sequence([NumberValue(90)])
        replacement_binding = Sequence([NumberValue(99)])
        first = DynamicContext({"base": first_binding})
        replacement = DynamicContext({"base": replacement_binding})
        iterator.open(first)
        try:
            first_result = iterator.next()
            iterator.next()
            iterator.reset(replacement)
            self.assertEqual(iterator.next(), first_result)
            values = [first_result]
            while True:
                try:
                    values.append(iterator.next())
                except StopIteration:
                    break
            stdout = io.StringIO()
            print_sequence(Sequence(values), file=stdout)
            self.assertEqual(stdout.getvalue(), case["stdout"])
            self.assertEqual(first.lookup("base"), first_binding)
            self.assertEqual(replacement.lookup("base"), replacement_binding)
            for context in (first, replacement):
                with self.assertRaisesRegex(DynamicError, "missing runtime binding: n"):
                    context.lookup("n")
        finally:
            iterator.close()
