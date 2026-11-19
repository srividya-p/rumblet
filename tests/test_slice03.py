"""Sequence boundaries, serialization, and query error reporting."""

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from rumblet.__main__ import main
from rumblet.errors import DynamicError, StaticError
from rumblet.sequence import Sequence, print_sequence
from rumblet.values import (
    NULL,
    ArrayValue,
    BooleanValue,
    NumberValue,
    ObjectValue,
    StringValue,
    Value,
)

ROOT = Path(__file__).resolve().parents[1]


class SequenceTests(unittest.TestCase):
    def test_sequence_is_a_list_of_values_not_a_value(self):
        source = [NumberValue(1), NULL]
        sequence = Sequence(source)
        source.clear()
        sequence.values.clear()
        self.assertEqual(sequence.values, [NumberValue(1), NULL])
        self.assertEqual(list(sequence), sequence.values)
        self.assertEqual(len(sequence), 2)
        self.assertNotIsInstance(sequence, Value)
        self.assertEqual(sequence, Sequence([NumberValue(1.0), NULL]))
        self.assertNotEqual(sequence, Sequence([NULL, NumberValue(1)]))
        self.assertNotEqual(sequence, ArrayValue([NumberValue(1), NULL]))

    def test_sequences_cannot_be_nested(self):
        for sequence in [Sequence([]), Sequence([NULL])]:
            with self.subTest(size=len(sequence)):
                with self.assertRaises(TypeError):
                    ArrayValue([sequence])
                with self.assertRaises(TypeError):
                    ObjectValue({"a": sequence})
                with self.assertRaises(DynamicError):
                    Sequence([sequence])
        for value in [None, 1, [], {}, Value()]:
            with self.subTest(value=repr(value)), self.assertRaises(DynamicError):
                Sequence([value])
        with self.assertRaises(DynamicError):
            Sequence((NULL,))

    def test_print_escapes_strings_and_sorts_objects(self):
        output = io.StringIO()
        print_sequence(Sequence([
            StringValue('line\n"quoted"\\😀'),
            ObjectValue({"z": NULL, "a": ArrayValue([])}),
            ArrayValue([]),
        ]), file=output)
        self.assertEqual(output.getvalue(),
                         '"line\\n\\"quoted\\"\\\\😀"\n{"a":[],"z":null}\n[]\n')
        self.assertEqual(len(output.getvalue().splitlines()), 3)
        with self.assertRaises(DynamicError):
            print_sequence(ArrayValue([]), file=output)

    def test_fixture_printing_and_query_cli(self):
        cases = json.loads((ROOT / "tests/queries/slice03/cases.json").read_text())["cases"]
        sequences = [
            Sequence([]),
            Sequence([StringValue("hello"), NumberValue(1), BooleanValue(True), NULL]),
            Sequence([
                ArrayValue([NumberValue(1), NULL]),
                ObjectValue({"items": ArrayValue([BooleanValue(False)])}),
            ]),
        ]
        for case, sequence in zip(cases, sequences, strict=True):
            with self.subTest(expression=case["expr"]):
                output = io.StringIO()
                with redirect_stdout(output):
                    print_sequence(sequence)
                self.assertEqual(output.getvalue(), case["printed_stdout"])
                cli = subprocess.run(
                    [sys.executable, "-m", "rumblet", "run", "--expr", case["expr"]],
                    cwd=ROOT, capture_output=True, text=True, check=False,
                )
                self.assertEqual((cli.returncode, cli.stdout, cli.stderr),
                                 (case["cli_exit_code"], case["cli_stdout"], case["cli_stderr"]))

    def test_cli_prints_engine_sequence(self):
        sequence = Sequence([StringValue("hello"), NumberValue(1), BooleanValue(True), NULL])
        with patch("rumblet.__main__.evaluate", return_value=sequence):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["run", "--expr", "placeholder"]), 0)
            self.assertEqual(output.getvalue(), '"hello"\n1\ntrue\nnull\n')

    def test_query_error_types_and_cli_reporting(self):
        self.assertFalse(issubclass(StaticError, DynamicError))
        for error_type in [StaticError, DynamicError]:
            with self.subTest(error=error_type.__name__):
                error = error_type("example failure")
                expected = f"{error_type.__name__}: example failure"
                self.assertEqual(str(error), expected)
                with patch("rumblet.__main__.evaluate", side_effect=error):
                    output, errors = io.StringIO(), io.StringIO()
                    with redirect_stdout(output), patch("sys.stderr", errors):
                        self.assertEqual(main(["run", "--expr", "placeholder"]), 2)
                    self.assertEqual(output.getvalue(), "")
                    self.assertEqual(errors.getvalue(), f"[rumblet] {expected}\n")
