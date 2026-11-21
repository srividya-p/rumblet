"""Regression cases for parsing, evaluation, and serialization limits."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from rumblet.errors import DynamicError
from rumblet.parser import (
    ArrayExpr,
    IfExpr,
    LiteralExpr,
    LogicalExpr,
    ObjectExpr,
    parse,
)
from rumblet.runtime import (
    ArithmeticIterator,
    CommaIterator,
    IfIterator,
    LiteralIterator,
)
from rumblet.values import BooleanValue, NumberValue

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests/queries/query_limits/cases.json").read_text())["cases"]


class QueryLimitTests(unittest.TestCase):
    def test_failed_close_hook_still_closes_active_child(self):
        class FailingIfIterator(IfIterator):
            def _close(self):
                raise RuntimeError("parent cleanup failed")

        class FailingLiteralIterator(LiteralIterator):
            def _close(self):
                closed.append(self)
                raise RuntimeError("child cleanup failed")

        closed = []
        child = FailingLiteralIterator(NumberValue(1))
        root = FailingIfIterator(
            LiteralIterator(BooleanValue(True)), child, LiteralIterator(NumberValue(0)),
        )
        root.open()
        self.assertEqual(root.next(), NumberValue(1))
        with self.assertRaisesRegex(RuntimeError, "parent cleanup failed"):
            root.close()
        self.assertEqual(closed, [child])
        for iterator in (root, child):
            with self.assertRaisesRegex(DynamicError, "iterator is not open"):
                iterator.next()
        root.close()
        self.assertEqual(closed, [child])

    def test_reset_and_close_deep_active_chain(self):
        leaf = LiteralIterator(NumberValue(1))
        root = leaf
        for _ in range(1500):
            root = IfIterator(
                LiteralIterator(BooleanValue(True)),
                CommaIterator((root, LiteralIterator(NumberValue(2)))),
                LiteralIterator(NumberValue(0)),
            )
        root.open()
        try:
            self.assertEqual(root.next(), NumberValue(1))
            root.reset()
            with self.assertRaisesRegex(DynamicError, "iterator is not open"):
                leaf.next()
            self.assertEqual(root.next(), NumberValue(1))
        finally:
            root.close()
        with self.assertRaisesRegex(DynamicError, "iterator is not open"):
            leaf.next()

    def test_failed_deep_pull_closes_temporary_operand(self):
        leaf = LiteralIterator(NumberValue(0))
        branch = ArithmeticIterator("div", (LiteralIterator(NumberValue(1)), leaf))
        for _ in range(1500):
            branch = IfIterator(
                LiteralIterator(BooleanValue(True)), branch, LiteralIterator(NumberValue(0)),
            )
        root = ArithmeticIterator("+", (branch,))
        root.open()
        try:
            with self.assertRaisesRegex(DynamicError, "division or remainder by zero"):
                root.next()
            for child in (branch, leaf):
                with self.assertRaisesRegex(DynamicError, "iterator is not open"):
                    child.next()
        finally:
            root.close()

    def test_deep_nested_ast(self):
        depth = 1500
        expression = '[{"x": if (not(false)) then ' * depth + '1' + ' else 0}]' * depth
        node = parse(expression)
        for _ in range(depth):
            self.assertIsInstance(node, ArrayExpr)
            (obj,) = node.elements
            self.assertIsInstance(obj, ObjectExpr)
            ((name, conditional),) = obj.members
            self.assertEqual(name, "x")
            self.assertIsInstance(conditional, IfExpr)
            self.assertIsInstance(conditional.test, LogicalExpr)
            self.assertEqual(conditional.test.operator, "not")
            self.assertEqual(conditional.else_branch, LiteralExpr(NumberValue(0)))
            node = conditional.then_branch
        self.assertEqual(node, LiteralExpr(NumberValue(1)))

    def test_query_cases(self):
        for index, case in enumerate(CASES, start=1):
            with self.subTest(case=index):
                result = subprocess.run(
                    [sys.executable, "-m", "rumblet", "run", "--expr", case["expr"]],
                    cwd=ROOT,
                    env={**os.environ, "PYTHONINTMAXSTRDIGITS": "4300"},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(
                    (result.returncode, result.stdout, result.stderr),
                    (case["exit_code"], case["stdout"], case["stderr"]),
                )
