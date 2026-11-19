"""Array constructor query cases and iterator lifecycle."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from rumblet.__main__ import main
from rumblet.errors import DynamicError
from rumblet.runtime import ArrayIterator, EmptySequenceIterator, LiteralIterator
from rumblet.values import NULL, ArrayValue

CASES = json.loads((Path(__file__).parent / "queries/slice10/cases.json").read_text())["cases"]


class ArrayConstructorTests(unittest.TestCase):
    def test_query_cases(self):
        for case in CASES:
            with self.subTest(expression=case["expr"]):
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(["run", "--expr", case["expr"]])
                self.assertEqual((exit_code, stdout.getvalue(), stderr.getvalue()),
                                 (case["exit_code"], case["stdout"], case["stderr"]))

    def test_iterator_emits_one_array_per_open_or_reset(self):
        element = LiteralIterator(NULL)
        iterator = ArrayIterator((element,))
        iterator.open()
        try:
            self.assertEqual(iterator.next(), ArrayValue([NULL]))
            with self.assertRaises(StopIteration):
                iterator.next()
            iterator.reset()
            self.assertEqual(iterator.next(), ArrayValue([NULL]))
        finally:
            iterator.close()

    def test_cardinality_error_closes_element_iterator(self):
        element = EmptySequenceIterator()
        iterator = ArrayIterator((element,))
        iterator.open()
        try:
            with self.assertRaisesRegex(DynamicError, "array element 1"):
                iterator.next()
            with self.assertRaisesRegex(DynamicError, "iterator is not open"):
                element.next()
        finally:
            iterator.close()
