"""Instance test query cases and iterator lifecycle."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from rumblet.__main__ import main
from rumblet.runtime import InstanceOfIterator, LiteralIterator
from rumblet.values import NULL, BooleanValue

CASES = json.loads((Path(__file__).parent / "queries/slice14/cases.json").read_text())["cases"]


class InstanceOfTests(unittest.TestCase):
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
        iterator = InstanceOfIterator(LiteralIterator(NULL), "number")
        iterator.open()
        try:
            self.assertEqual(iterator.next(), BooleanValue(False))
            with self.assertRaises(StopIteration):
                iterator.next()
            iterator.reset()
            self.assertEqual(iterator.next(), BooleanValue(False))
        finally:
            iterator.close()
