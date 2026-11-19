"""Object constructor query cases and runtime lifecycle."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from rumblet.__main__ import main
from rumblet.engine import evaluate
from rumblet.errors import DynamicError, StaticError
from rumblet.runtime import LiteralIterator, ObjectIterator
from rumblet.values import NULL, ObjectValue

CASES = json.loads((Path(__file__).parent / "queries/slice09/cases.json").read_text())["cases"]


class ObjectConstructorTests(unittest.TestCase):
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
                    values = evaluate(expr).values
                    self.assertTrue(all(isinstance(value, ObjectValue) for value in values))
                    self.assertEqual([value.value for value in values],
                                     [json.loads(line) for line in case["stdout"].splitlines()])

    def test_iterator_emits_one_object_per_open_or_reset(self):
        member = LiteralIterator(NULL)
        iterator = ObjectIterator((("a", member),))
        iterator.open()
        try:
            self.assertEqual(iterator.next(), ObjectValue({"a": NULL}))
            with self.assertRaises(StopIteration):
                iterator.next()
            with self.assertRaisesRegex(DynamicError, "iterator is not open"):
                member.next()
            iterator.reset()
            self.assertEqual(iterator.next(), ObjectValue({"a": NULL}))
        finally:
            iterator.close()
