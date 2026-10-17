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
"""Unit tests for the test-run completeness check and the report reader."""

import tempfile
import unittest
from pathlib import Path

from quality.gtest_tool_confidence.common import gtest_report
from quality.gtest_tool_confidence.completeness import check_test_run_completeness as check

_GOOD = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites tests="3" failures="1" disabled="0" errors="0" name="AllTests">
  <testsuite name="Suite" tests="3">
    <testcase name="Passes" file="a.cpp" line="1" status="run" result="completed" classname="Suite">
      <properties><property name="PartiallyVerifies" value="comp_req__x"/></properties>
    </testcase>
    <testcase name="Fails" status="run" result="completed" classname="Suite">
      <failure message="a.cpp:2 boom" type=""/>
    </testcase>
    <testcase name="Skips" status="run" result="skipped" classname="Suite">
      <skipped message="later"/>
    </testcase>
  </testsuite>
</testsuites>
"""

_COUNT_MISMATCH = _GOOD.replace('<testsuites tests="3"', '<testsuites tests="4"')

_SKIPPED_WITH_LINK = _GOOD.replace(
    '<skipped message="later"/>',
    '<properties><property name="FullyVerifies" value="comp_req__y"/></properties><skipped message="later"/>',
)

_ERROR_ELEMENT = _GOOD.replace('<failure message="a.cpp:2 boom" type=""/>', '<error message="crash"/>')

_EMPTY_GTEST = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites tests="0" name="AllTests"></testsuites>
"""

_BAZEL_FALLBACK = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="pkg/py_test" tests="1" failures="0" errors="0">
    <testcase name="pkg/py_test" status="run" duration="1" time="1"></testcase>
  </testsuite>
</testsuites>
"""

_DUPLICATE = _GOOD.replace('name="Fails"', 'name="Passes"')


class ReportReaderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, content, rel="test.xml"):
        path = self.dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_classifies_like_docs_as_code(self):
        results = gtest_report.parse_report(self._write(_GOOD))
        self.assertEqual(results["Suite.Passes"].result, "passed")
        self.assertEqual(results["Suite.Fails"].result, "failed")
        self.assertEqual(results["Suite.Skips"].result, "skipped")
        self.assertEqual(results["Suite.Passes"].properties, {"PartiallyVerifies": "comp_req__x"})

    def test_notrun_is_disabled(self):
        xml = _GOOD.replace('name="Passes" file="a.cpp" line="1" status="run"', 'name="Passes" status="notrun"')
        self.assertEqual(gtest_report.parse_report(self._write(xml))["Suite.Passes"].result, "disabled")

    def test_error_element_is_failed(self):
        self.assertEqual(gtest_report.parse_report(self._write(_ERROR_ELEMENT))["Suite.Fails"].result, "failed")

    def test_property_attributes_of_old_gtest_versions(self):
        xml = _GOOD.replace('classname="Suite">\n      <properties>', 'classname="Suite" ASIL="B">\n      <properties>', 1)
        self.assertEqual(gtest_report.parse_report(self._write(xml))["Suite.Passes"].properties["ASIL"], "B")

    def test_duplicate_testcase_is_rejected(self):
        with self.assertRaises(ValueError):
            gtest_report.parse_report(self._write(_DUPLICATE))

    def test_parse_test_list(self):
        output = (
            "Suite.\n"
            "  Passes\n"
            "Values/Param.\n"
            "  Case/0  # GetParam() = 1\n"
            "Typed/0.  # TypeParam = int\n"
            "  Case\n"
        )
        self.assertEqual(
            gtest_report.parse_test_list(output),
            ["Suite.Passes", "Values/Param.Case/0", "Typed/0.Case"],
        )

    def test_parse_test_list_skips_gtest_main_banner(self):
        output = "Running main() from gmock_main.cc\nSuite.\n  Passes\n"
        self.assertEqual(gtest_report.parse_test_list(output), ["Suite.Passes"])

    def test_parse_test_list_rejects_banner_after_first_suite(self):
        with self.assertRaises(ValueError):
            gtest_report.parse_test_list("Suite.\n  Passes\nRunning main() from gmock_main.cc\n")

    def test_parse_test_list_rejects_garbage(self):
        with self.assertRaises(ValueError):
            gtest_report.parse_test_list("not a suite line\n")


class CompletenessCheckTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.logs = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _report(self, content, target="pkg/unit_test"):
        path = self.logs / target / "test.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _messages(self, findings, severity="error"):
        return [f.message for f in findings if f.severity == severity]

    def test_consistent_report_has_no_errors(self):
        self._report(_GOOD)
        reports, findings = check.check_testlogs(self.logs)
        self.assertEqual(len(reports), 1)
        self.assertEqual(self._messages(findings), [])

    def test_declared_count_mismatch_is_error(self):
        self._report(_COUNT_MISMATCH)
        _, findings = check.check_testlogs(self.logs)
        self.assertIn("report declares 4 tests but contains 3", self._messages(findings))

    def test_error_element_is_error(self):
        self._report(_ERROR_ELEMENT)
        _, findings = check.check_testlogs(self.logs)
        self.assertIn("Suite.Fails has an <error> element", self._messages(findings))

    def test_empty_gtest_report_is_error(self):
        self._report(_EMPTY_GTEST)
        _, findings = check.check_testlogs(self.logs)
        self.assertIn("GoogleTest report without test cases", self._messages(findings))

    def test_unreadable_report_is_error(self):
        self._report("<testsuites><testsuite>")
        _, findings = check.check_testlogs(self.logs)
        self.assertTrue(any(m.startswith("unreadable report") for m in self._messages(findings)))

    def test_bazel_fallback_report_is_ignored(self):
        self._report(_BAZEL_FALLBACK, target="pkg/py_test")
        _, findings = check.check_testlogs(self.logs)
        self.assertEqual(findings, [])

    def test_skipped_with_requirement_link_is_warning_by_default(self):
        self._report(_SKIPPED_WITH_LINK)
        _, findings = check.check_testlogs(self.logs)
        self.assertEqual(self._messages(findings), [])
        self.assertIn("Suite.Skips is skipped but declares FullyVerifies", self._messages(findings, "warning"))

    def test_skipped_with_requirement_link_can_be_error(self):
        self._report(_SKIPPED_WITH_LINK)
        _, findings = check.check_testlogs(self.logs, fail_on_skipped_verification=True)
        self.assertIn("Suite.Skips is skipped but declares FullyVerifies", self._messages(findings))

    def test_shard_directory_maps_to_target(self):
        path = self._report(_GOOD, target="pkg/unit_test/shard_1_of_2")
        self.assertEqual(check._target_of(self.logs, path), "pkg/unit_test")

    def test_main_without_reports_fails(self):
        self.assertEqual(check.main(["--testlogs", str(self.logs)]), 1)

    def test_main_with_clean_report_passes(self):
        self._report(_GOOD)
        self.assertEqual(check.main(["--testlogs", str(self.logs)]), 0)


if __name__ == "__main__":
    unittest.main()
