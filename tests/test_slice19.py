"""Static function calls with built-ins and test-only callables."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from rumblet.__main__ import main
from rumblet.engine import evaluate
from rumblet.errors import DynamicError
from rumblet.sequence import Sequence, print_sequence
from rumblet.values import NumberValue

CASES = json.loads((Path(__file__).parent / "queries/slice19/cases.json").read_text())["cases"]


class FunctionCallTests(unittest.TestCase):
    def test_cli_cases(self):
        for case in CASES:
            if case.get("registered"):
                continue
            with self.subTest(expression=case["expr"]):
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(["run", "--expr", case["expr"]])
                self.assertEqual(
                    (exit_code, stdout.getvalue(), stderr.getvalue()),
                    (case["exit_code"], case["stdout"], case["stderr"]),
                )

    def test_registered_function_cases(self):
        for case in CASES:
            if not case.get("registered"):
                continue
            with self.subTest(expression=case["expr"]):
                calls = []

                def record(name, *arguments, calls=calls):
                    for argument in arguments:
                        self.assertIsInstance(argument, Sequence)
                    calls.append([name, [[value.value for value in arg] for arg in arguments]])
                    if name == "zero":
                        return Sequence([NumberValue(0)])
                    return Sequence([value for arg in arguments for value in arg])

                functions = {
                    "mark": lambda *args: record("mark", *args),
                    "gather": lambda *args: record("gather", *args),
                    "zero": lambda *args: record("zero", *args),
                }
                stdout = io.StringIO()
                if "dynamic_error" in case:
                    with self.assertRaisesRegex(DynamicError, case["dynamic_error"]):
                        evaluate(case["expr"], functions=functions)
                else:
                    print_sequence(evaluate(case["expr"], functions=functions), file=stdout)
                self.assertEqual(stdout.getvalue(), case["stdout"])
                self.assertEqual(calls, case["calls"])
