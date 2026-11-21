"""Regression cases for parsing, evaluation, and serialization limits."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from rumblet.parser import (
    ArrayExpr,
    IfExpr,
    LiteralExpr,
    LogicalExpr,
    ObjectExpr,
    parse,
)
from rumblet.values import NumberValue

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests/queries/query_limits/cases.json").read_text())["cases"]


class QueryLimitTests(unittest.TestCase):
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
