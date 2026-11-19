"""Runtime lifecycle, literal pulling, and dynamic context bindings."""

import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

from rumblet.context import DynamicContext
from rumblet.errors import DynamicError
from rumblet.runtime import LiteralIterator, RuntimeIterator
from rumblet.sequence import Sequence, print_sequence
from rumblet.values import (
    NULL,
    ArrayValue,
    BooleanValue,
    NumberValue,
    ObjectValue,
    StringValue,
)

ROOT = Path(__file__).resolve().parents[1]


class ContextReader(RuntimeIterator):
    """Test iterator proving hooks and pulls can access the active context."""

    def _restart(self):
        self.context.bind("ready", Sequence([BooleanValue(True)]))
        self.position = 0

    def _next(self):
        values = self.context.lookup("x").values
        if self.position >= len(values):
            raise StopIteration
        value = values[self.position]
        self.position += 1
        return value


class RuntimeTests(unittest.TestCase):
    def test_literal_lifecycle_and_all_value_kinds(self):
        for value in [NumberValue(1), StringValue(""), BooleanValue(False), NULL,
                      ArrayValue([]), ObjectValue({})]:
            with self.subTest(kind=value.kind):
                iterator = LiteralIterator(value)
                for operation in [iterator.next, iterator.reset]:
                    with self.assertRaises(DynamicError):
                        operation()
                iterator.close()
                iterator.open()
                with self.assertRaises(DynamicError):
                    iterator.open()
                self.assertEqual(iterator.next(), value)
                for _ in range(2):
                    with self.assertRaises(StopIteration):
                        iterator.next()
                iterator.reset()
                self.assertEqual(iterator.next(), value)
                iterator.reset()  # Reset also works before observing exhaustion.
                self.assertEqual(iterator.next(), value)
                iterator.close()
                iterator.close()
                with self.assertRaises(DynamicError):
                    iterator.next()
                iterator.open()
                self.assertEqual(iterator.next(), value)
                iterator.close()

    def test_context_install_update_and_replace(self):
        context = DynamicContext({"keep": Sequence([NULL])})
        iterator = ContextReader()
        iterator.open(context, bindings={"x": Sequence([NumberValue(1), NumberValue(2)])})
        self.assertIs(iterator.context, context)
        self.assertEqual(context.lookup("ready"), Sequence([BooleanValue(True)]))
        self.assertEqual(iterator.next(), NumberValue(1))
        # Pulls read current bindings, rather than a copy made at open().
        context.bind("x", Sequence([NumberValue(3), NumberValue(4)]))
        self.assertEqual(iterator.next(), NumberValue(4))
        with self.assertRaises(StopIteration):
            iterator.next()
        iterator.reset(bindings={"x": Sequence([NULL])})
        self.assertIs(iterator.context, context)
        self.assertEqual(context.lookup("keep"), Sequence([NULL]))
        self.assertEqual(iterator.next(), NULL)
        replacement = DynamicContext()
        iterator.reset(replacement, bindings={"x": Sequence([StringValue("new")])})
        self.assertIs(iterator.context, replacement)
        self.assertEqual(iterator.next(), StringValue("new"))
        iterator.close()
        self.assertEqual(replacement.lookup("x"), Sequence([StringValue("new")]))

    def test_context_validation_and_empty_sequence_binding(self):
        source = {"x": Sequence([])}
        context = DynamicContext(source)
        source.clear()
        self.assertEqual(context.lookup("x"), Sequence([]))
        with self.assertRaises(DynamicError):
            context.lookup("missing")
        for bindings in [{"bad": NULL}, {1: Sequence([])}, []]:
            with self.subTest(bindings=bindings), self.assertRaises(DynamicError):
                context.update(bindings)
        with self.assertRaises(DynamicError):
            context.update({"x": Sequence([NULL]), "bad": NULL})
        self.assertEqual(context.lookup("x"), Sequence([]))
        iterator = LiteralIterator(NULL)
        with self.assertRaises(DynamicError):
            iterator.open(context={})
        iterator.open(bindings={"x": Sequence([])})
        self.assertEqual(iterator.context.lookup("x"), Sequence([]))
        iterator.close()

    def test_literal_rejects_sequences_and_raw_values(self):
        for invalid in [Sequence([]), None, 1, [], {}]:
            with self.subTest(value=repr(invalid)), self.assertRaises(DynamicError):
                LiteralIterator(invalid)

    def test_close_hook_and_context_release(self):
        class Tracked(ContextReader):
            closes = 0

            def _close(self):
                self.context.bind("closed", Sequence([NULL]))
                self.closes += 1

        context = DynamicContext()
        iterator = Tracked()
        iterator.open(context)
        iterator.close()
        iterator.close()
        self.assertEqual(iterator.closes, 1)
        self.assertEqual(context.lookup("closed"), Sequence([NULL]))
        with self.assertRaises(DynamicError):
            _ = iterator.context

    def test_literal_query_fixtures(self):
        cases = json.loads((ROOT / "tests/queries/slice04/cases.json").read_text())["cases"]
        for case in cases:
            with self.subTest(expression=case["expr"]):
                raw = case["literal"]
                value = NULL if raw is None else (
                    StringValue(raw) if type(raw) is str else NumberValue(raw))
                iterator = LiteralIterator(value)
                iterator.open()
                values = []
                try:
                    while True:
                        values.append(iterator.next())
                except StopIteration:
                    pass
                finally:
                    iterator.close()
                output = io.StringIO()
                print_sequence(Sequence(values), file=output)
                self.assertEqual(output.getvalue(), case["printed_stdout"])
                cli = subprocess.run(
                    [sys.executable, "-m", "rumblet", "run", "--expr", case["expr"]],
                    cwd=ROOT, capture_output=True, text=True, check=False,
                )
                self.assertEqual((cli.returncode, cli.stdout, cli.stderr),
                                 (case["cli_exit_code"], case["cli_stdout"], case["cli_stderr"]))
