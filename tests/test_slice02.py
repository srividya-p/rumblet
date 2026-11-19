"""Containers, nesting, and content-based value identity."""

import json
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from rumblet.values import (
    NULL,
    ArrayValue,
    BooleanValue,
    NullValue,
    NumberValue,
    ObjectValue,
    StringValue,
    Value,
)

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests/queries/slice02/cases.json").read_text())["cases"]


def model(value):
    """Build test values from JSON fixture contents without parsing query syntax."""
    if value is None:
        return NullValue()
    if type(value) is bool:
        return BooleanValue(value)
    if type(value) in (int, float):
        return NumberValue(value)
    if type(value) is str:
        return StringValue(value)
    if type(value) is list:
        return ArrayValue([model(item) for item in value])
    return ObjectValue({name: model(item) for name, item in value.items()})


class ContainerValueTests(unittest.TestCase):
    def test_fixture_model_contents_and_cli(self):
        for case in CASES:
            with self.subTest(expression=case["expr"]):
                value = model(case["model_value"])
                self.assertEqual(value.value, case["model_value"])
                self.assertEqual(json.loads(json.dumps(value.value, allow_nan=False)),
                                 case["model_value"])
                self.assertEqual(value, model(case["model_value"]))
                result = subprocess.run(
                    [sys.executable, "-m", "rumblet", "run", "--expr", case["expr"]],
                    cwd=ROOT, capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, case["exit_code"])
                self.assertEqual(result.stdout, case["stdout"])
                self.assertEqual(result.stderr, case["stderr"])

    def test_array_order_and_length(self):
        self.assertEqual(len(ArrayValue([])), 0)
        self.assertEqual(ArrayValue([]).kind, "array")
        self.assertNotEqual(model([1, 2]), model([2, 1]))
        self.assertNotEqual(model([1]), model([1, 1]))
        self.assertNotEqual(model([True]), model([1]))

    def test_object_order_and_member_names(self):
        self.assertEqual(ObjectValue({}).kind, "object")
        first = ObjectValue([("a", NumberValue(1)), ("b", NULL)])
        second = ObjectValue([("b", NullValue()), ("a", NumberValue(1.0))])
        self.assertEqual(first, second)
        self.assertEqual(hash(first), hash(second))
        self.assertNotEqual(model({"a": 1}), model({"b": 1}))
        self.assertNotEqual(model({"a": True}), model({"a": 1}))
        self.assertNotEqual(model({}), model({"a": None}))
        self.assertEqual(model({"": None, "😀": 1}).value, {"": None, "😀": 1})

    def test_duplicate_and_invalid_names(self):
        with self.assertRaises(ValueError):
            ObjectValue([("a", NULL), ("a", NumberValue(1))])
        with self.assertRaises(TypeError):
            ObjectValue({1: NULL})
        with self.assertRaises(ValueError):
            ObjectValue({"\ud800": NULL})

    def test_only_model_values_can_be_nested(self):
        for invalid in [None, True, 1, "text", [], {}, (), Value()]:
            with self.subTest(value=repr(invalid)):
                with self.assertRaises(TypeError):
                    ArrayValue([invalid])
                with self.assertRaises(TypeError):
                    ObjectValue({"a": invalid})
        with self.assertRaises(TypeError):
            ArrayValue((NULL,))
        with self.assertRaises(TypeError):
            ObjectValue(())

    def test_nesting_and_content_identity(self):
        first = model({"a": ["text", 1, True, None, {}, []]})
        second = model({"a": ["text", 1.0, True, None, {}, []]})
        self.assertIsNot(first, second)
        self.assertEqual(first, second)
        self.assertEqual(hash(first), hash(second))
        self.assertNotEqual(first, model({"a": ["text", 1, False, None, {}, []]}))
        self.assertNotEqual(ArrayValue([]), ObjectValue({}))
        value = NULL
        for _ in range(50):
            value = ObjectValue({"nested": ArrayValue([value])})
        self.assertEqual(value, value)

    def test_containers_cannot_be_mutated_through_inputs_or_payloads(self):
        elements = [NULL]
        array = ArrayValue(elements)
        elements.append(NumberValue(1))
        members = {"a": array}
        obj = ObjectValue(members)
        members.clear()
        payload = obj.value
        payload["a"].append(1)
        obj.members.clear()
        self.assertEqual(obj.value, {"a": [None]})
        self.assertEqual(array.elements, (NULL,))
        with self.assertRaises(FrozenInstanceError):
            array._elements = ()
        for value in [array, obj]:
            with self.assertRaises(TypeError):
                bool(value)
