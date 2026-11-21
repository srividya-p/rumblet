"""Where clause query cases and iterator reset behavior."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from rumblet.__main__ import main
from rumblet.engine import _build_iterator
from rumblet.parser import parse
from rumblet.values import NumberValue

CASES = json.loads((Path(__file__).parent / "queries/slice17/cases.json").read_text())["cases"]


class WhereTests(unittest.TestCase):
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

    def test_reset_reapplies_filter(self):
        iterator = _build_iterator(parse("for $x in (1,2,3) where $x gt 1 return $x"))
        iterator.open()
        try:
            self.assertEqual(iterator.next(), NumberValue(2))
            iterator.reset()
            self.assertEqual(iterator.next(), NumberValue(2))
            self.assertEqual(iterator.next(), NumberValue(3))
            with self.assertRaises(StopIteration):
                iterator.next()
        finally:
            iterator.close()
