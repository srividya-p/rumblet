"""Exercise json-file through the CLI with temporary input files."""

import io
import json
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from rumblet.__main__ import main

CASES = json.loads(
    (Path(__file__).parent / "queries/slice20/cases.json").read_text(encoding="utf-8")
)["cases"]


class JsonFileTests(unittest.TestCase):
    def test_query_cases(self):
        for case in CASES:
            with self.subTest(expression=case["expr"]), TemporaryDirectory() as directory:
                for name, content in case.get("files", {}).items():
                    (Path(directory) / name).write_text(content, encoding="utf-8")
                stdout, stderr = io.StringIO(), io.StringIO()
                with chdir(directory), redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(["run", "--expr", case["expr"]])
                self.assertEqual(
                    (exit_code, stdout.getvalue(), stderr.getvalue()),
                    (case.get("exit_code", 0), case["stdout"], case.get("stderr", "")),
                )
