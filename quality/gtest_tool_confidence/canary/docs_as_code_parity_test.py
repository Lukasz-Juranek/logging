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
"""The canary checker classifies results exactly like docs-as-code.

The checker re-implements the result classification of docs-as-code so that it
stays small and free of Sphinx dependencies. This test runs the real
docs-as-code parser (parse_testcase_result of the docs-as-code version used by
this repository) on the XML reports of all canary binaries and on synthetic
edge cases, and requires identical results. A docs-as-code update that changes
the classification fails here.

Usage: docs_as_code_parity_test.py <binary> ...
"""

import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from src.extensions.score_source_code_linker.xml_parser import parse_testcase_result

from quality.gtest_tool_confidence.common import gtest_report

_BINARIES = []

_EDGE_CASES = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="AllTests">
  <testsuite name="Edge">
    <testcase name="Passed" status="run" classname="Edge"/>
    <testcase name="Failed" status="run" classname="Edge"><failure message="f"/></testcase>
    <testcase name="Error" status="run" classname="Edge"><error message="e"/></testcase>
    <testcase name="Skipped" status="run" classname="Edge"><skipped message="s"/></testcase>
    <testcase name="NotRun" status="notrun" classname="Edge"/>
    <testcase name="NotRunWithFailure" status="notrun" classname="Edge"><failure message="f"/></testcase>
    <testcase name="FailedAndSkipped" status="run" classname="Edge"><skipped/><failure message="f"/></testcase>
    <testcase name="ErrorAndSkipped" status="run" classname="Edge"><skipped/><error message="e"/></testcase>
    <testcase name="FailureAndError" status="run" classname="Edge"><error message="e"/><failure message="f"/></testcase>
    <testcase name="NoStatus" classname="Edge"/>
    <testcase name="" status="run" classname=""><failure message="suite-level"/></testcase>
  </testsuite>
</testsuites>
"""


def _compare(root):
    """Return the mismatches between both classifications for a report root."""
    mismatches = []
    for key, testcase in gtest_report.iter_testcases(root):
        ours = gtest_report.classify(testcase)
        theirs = parse_testcase_result(testcase)
        if ours != theirs:
            mismatches.append(f"{key}: checker {ours}, docs-as-code {theirs}")
    return mismatches


class DocsAsCodeParityTest(unittest.TestCase):
    def test_edge_cases(self):
        self.assertEqual(_compare(ET.fromstring(_EDGE_CASES)), [])

    def test_canary_reports(self):
        self.assertTrue(_BINARIES, "no canary binaries given")
        compared = 0
        for binary in _BINARIES:
            with self.subTest(binary=binary.name), tempfile.TemporaryDirectory() as tmp:
                xml_path = Path(tmp) / "report.xml"
                gtest_report.run_with_report(binary, xml_path, cwd=tmp)
                if not xml_path.exists():
                    continue  # premature exit: no report to classify
                root = ET.parse(xml_path).getroot()
                compared += len(list(gtest_report.iter_testcases(root)))
                self.assertEqual(_compare(root), [])
        self.assertGreater(compared, 0)


if __name__ == "__main__":
    _BINARIES.extend(Path(arg).resolve() for arg in sys.argv[1:])
    unittest.main(argv=sys.argv[:1], verbosity=2)
