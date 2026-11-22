"""Exercise query file input through the command-line entry point."""

import io
import json
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from rumblet.__main__ import main

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads(
    (ROOT / "tests/queries/cli/cases.json").read_text(encoding="utf-8")
)["cases"]


def run_cli(*args):
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = main(["run", *args])
    return exit_code, stdout.getvalue(), stderr.getvalue()


class QueryFileTests(unittest.TestCase):
    def test_readme_query_files(self):
        with chdir(ROOT):
            for case in CASES:
                with self.subTest(file=case["file"]):
                    self.assertEqual(
                        run_cli("--file", case["file"]), (0, case["stdout"], "")
                    )

    def test_query_sources_are_mutually_exclusive_and_required(self):
        for args in [(), ("--expr", "1", "--file", "example.rq")]:
            with self.subTest(args=args), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(["run", *args])
                self.assertEqual(error.exception.code, 2)

    def test_relative_data_path_and_optional_extension(self):
        with TemporaryDirectory() as directory, chdir(directory):
            Path("queries").mkdir()
            Path("queries/example").write_text(
                'json-file("data.json"), "café"\n', encoding="utf-8"
            )
            Path("data.json").write_text("42", encoding="utf-8")
            self.assertEqual(
                run_cli("--file", "queries/example"), (0, '42\n"café"\n', "")
            )

    def test_file_read_errors(self):
        with TemporaryDirectory() as directory, chdir(directory):
            Path("invalid.rq").write_bytes(bytes([255]))
            Path("directory.rq").mkdir()
            for name in ("missing.rq", "invalid.rq", "directory.rq"):
                with self.subTest(file=name):
                    status, stdout, stderr = run_cli("--file", name)
                    self.assertEqual((status, stdout), (2, ""))
                    self.assertIn(f"cannot read query file {name!r}", stderr)

    def test_file_uses_inline_query_grammar(self):
        with TemporaryDirectory() as directory, chdir(directory):
            for expression in ("", "1\n2", "1; 2", "1 div 0"):
                with self.subTest(expression=expression):
                    Path("query.rq").write_text(expression, encoding="utf-8")
                    expected = run_cli("--expr", expression)
                    self.assertEqual(expected[0], 2)
                    self.assertEqual(run_cli("--file", "query.rq"), expected)
