"""Atomic model conformance and query fixtures for the CLI."""

import json
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from rumblet.values import NULL, BooleanValue, NullValue, NumberValue, StringValue

ROOT = Path(__file__).resolve().parents[1]


class AtomicValueTests(unittest.TestCase):
    def test_string_scalar_length_and_equality(self):
        for text, length in [("", 0), ("hello", 5), ("a😀", 2), ("e\u0301", 2)]:
            with self.subTest(text=text):
                self.assertEqual(len(StringValue(text)), length)
                self.assertEqual(StringValue(text), StringValue(text))
        self.assertNotEqual(StringValue("ab"), StringValue("ba"))
        self.assertNotEqual(StringValue("é"), StringValue("e\u0301"))

    def test_string_rejects_non_scalars(self):
        for text in ["\ud800", "\udfff", "\ud83d\ude00"]:
            with self.subTest(text=repr(text)), self.assertRaises(ValueError):
                StringValue(text)
        with self.assertRaises(TypeError):
            StringValue(1)

    def test_number_mathematical_equality(self):
        self.assertEqual(NumberValue(1), NumberValue(1.0))
        self.assertEqual(hash(NumberValue(1)), hash(NumberValue(1.0)))
        self.assertEqual(NumberValue(0), NumberValue(-0.0))
        self.assertNotEqual(NumberValue(1), NumberValue(2))
        self.assertEqual(NumberValue(10**100).value, 10**100)
        self.assertEqual(NumberValue(1.25).value, 1.25)

    def test_number_rejects_invalid_content(self):
        for value in [True, False, "1", None, (), [], {}, complex(1, 2)]:
            with self.subTest(value=value), self.assertRaises(TypeError):
                NumberValue(value)
        for text in ["NaN", "Infinity", "-Infinity"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                NumberValue(float(text))

    def test_booleans_and_distinct_kinds(self):
        self.assertEqual(BooleanValue(True), BooleanValue(True))
        self.assertNotEqual(BooleanValue(True), BooleanValue(False))
        values = [BooleanValue(True), NumberValue(1), StringValue("1"), NULL]
        self.assertEqual(len(set(values)), 4)
        self.assertEqual([v.kind for v in values], ["boolean", "number", "string", "null"])
        for value in [0, 1, "true", None]:
            with self.subTest(value=value), self.assertRaises(TypeError):
                BooleanValue(value)

    def test_null_has_only_one_value(self):
        self.assertEqual(NULL, NullValue())
        self.assertEqual(hash(NULL), hash(NullValue()))
        self.assertIsNone(NULL.value)
        with self.assertRaises(TypeError):
            len(NULL)
        with self.assertRaises(TypeError):
            NullValue(None)

    def test_immutability_and_no_implicit_truth(self):
        for value in [StringValue(""), NumberValue(0), BooleanValue(False), NULL]:
            with self.subTest(kind=value.kind), self.assertRaises(TypeError):
                bool(value)
        value = StringValue("original")
        with self.assertRaises(FrozenInstanceError):
            value.value = "changed"

    def test_payloads_round_trip_as_json(self):
        for value, expected in [
            (StringValue("hello"), '"hello"'),
            (NumberValue(1), "1"),
            (NumberValue(1.25), "1.25"),
            (BooleanValue(True), "true"),
            (BooleanValue(False), "false"),
            (NULL, "null"),
        ]:
            with self.subTest(kind=value.kind, expected=expected):
                encoded = json.dumps(value.value, allow_nan=False)
                self.assertEqual(encoded, expected)
                self.assertEqual(json.loads(encoded), value.value)
                self.assertIs(type(json.loads(encoded)), type(value.value))

    def test_query_fixtures(self):
        cases = json.loads((ROOT / "tests/queries/slice01/cases.json").read_text())["cases"]
        for case in cases:
            with self.subTest(expression=case["expr"]):
                result = subprocess.run(
                    [sys.executable, "-m", "rumblet", "run", "--expr", case["expr"]],
                    cwd=ROOT, capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, case["exit_code"])
                self.assertEqual(result.stdout, case["stdout"])
                self.assertEqual(result.stderr, case["stderr"])
