"""Effective boolean values of evaluated query sequences."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from rumblet.__main__ import main
from rumblet.engine import evaluate
from rumblet.errors import DynamicError
from rumblet.runtime import effective_boolean_value
from rumblet.sequence import Sequence, print_sequence
from rumblet.values import BooleanValue

CASES = json.loads((Path(__file__).parent / "queries/slice11/cases.json").read_text())["cases"]


class EffectiveBooleanValueTests(unittest.TestCase):
    def test_query_cases(self):
        for case in CASES:
            if "stdout" in case:
                continue
            with self.subTest(expression=case["expr"]):
                sequence = evaluate(case["expr"])
                if "error" in case:
                    with self.assertRaises(DynamicError) as raised:
                        effective_boolean_value(sequence)
                    self.assertEqual(type(raised.exception).__name__, case["error"])
                else:
                    self.assertIs(effective_boolean_value(sequence), case["result"])

    def test_logical_query_cases(self):
        for case in CASES:
            if "stdout" not in case or case.get("registered"):
                continue
            with self.subTest(expression=case["expr"]):
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(["run", "--expr", case["expr"]])
                self.assertEqual(
                    (exit_code, stdout.getvalue(), stderr.getvalue()),
                    (case.get("exit_code", 0), case["stdout"], case.get("stderr", "")),
                )

    def test_registered_logical_operands_are_eager_and_left_to_right(self):
        for case in CASES:
            if not case.get("registered"):
                continue
            calls = []

            def function(name, result):
                def invoke():
                    calls.append(name)
                    return Sequence([BooleanValue(result)])
                return invoke

            functions = {
                "left": function("left", False),
                "right": function("right", True),
            }
            output = io.StringIO()
            print_sequence(evaluate(case["expr"], functions=functions), file=output)
            self.assertEqual((output.getvalue(), calls), (case["stdout"], case["calls"]))
