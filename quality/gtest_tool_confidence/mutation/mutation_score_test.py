# *******************************************************************************
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************
"""Unit tests for mutation_score.py."""

import json
import tempfile
import unittest
from pathlib import Path

from quality.gtest_tool_confidence.mutation import mutation_score


def _mutant(status, line=1, mutator="cxx_add_to_sub"):
    return {"mutatorName": mutator, "status": status, "location": {"start": {"line": line, "column": 3}}}


_REPORT = {
    "files": {
        "score/a.cpp": {"mutants": [_mutant("Killed"), _mutant("Killed"), _mutant("Timeout"), _mutant("Survived", 7)]},
        "score/b.cpp": {"mutants": [_mutant("NoCoverage", 9, "cxx_remove_void_call")]},
    }
}


class MutationScoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, report):
        path = self.dir / "report.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    def test_score_counts_timeout_as_detected_and_nocoverage_as_undetected(self):
        score, counts, undetected = mutation_score.evaluate(_REPORT)
        self.assertAlmostEqual(score, 60.0)
        self.assertEqual(counts, {"Killed": 2, "Timeout": 1, "Survived": 1, "NoCoverage": 1})
        self.assertEqual(
            undetected,
            [
                ("score/a.cpp", 7, 3, "cxx_add_to_sub", "Survived"),
                ("score/b.cpp", 9, 3, "cxx_remove_void_call", "NoCoverage"),
            ],
        )

    def test_threshold_decides_exit_code(self):
        path = self._write(_REPORT)
        self.assertEqual(mutation_score.main(["--elements", str(path), "--threshold", "60"]), 0)
        self.assertEqual(mutation_score.main(["--elements", str(path), "--threshold", "61"]), 1)

    def test_markdown_lists_undetected_mutants(self):
        path = self._write(_REPORT)
        markdown = self.dir / "summary.md"
        mutation_score.main(["--elements", str(path), "--markdown", str(markdown)])
        text = markdown.read_text(encoding="utf-8")
        self.assertIn("| score/a.cpp | 7:3 | cxx_add_to_sub | Survived | |", text)
        self.assertIn("**60.0 %**", text)

    def test_empty_report_is_bad_input(self):
        path = self._write({"files": {}})
        self.assertEqual(mutation_score.main(["--elements", str(path)]), 2)

    def test_unreadable_report_is_bad_input(self):
        self.assertEqual(mutation_score.main(["--elements", str(self.dir / "missing.json")]), 2)


if __name__ == "__main__":
    unittest.main()
