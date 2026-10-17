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

import stat
import sys
import tempfile
import unittest
from pathlib import Path

from quality.gtest_tool_confidence.common import gtest_report
from quality.gtest_tool_confidence.completeness import check_test_run_completeness as check

_GOOD = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites tests="3" failures="0" disabled="0" errors="0" name="AllTests">
  <testsuite name="Suite" tests="3">
    <testcase name="Passes" file="a.cpp" line="1" status="run" result="completed" classname="Suite">
      <properties><property name="PartiallyVerifies" value="comp_req__x"/></properties>
    </testcase>
    <testcase name="AlsoPasses" status="run" result="completed" classname="Suite">
    </testcase>
    <testcase name="Skips" status="run" result="skipped" classname="Suite">
      <skipped message="later"/>
    </testcase>
  </testsuite>
</testsuites>
"""
_GOOD_KEYS = ["Suite.Passes", "Suite.AlsoPasses", "Suite.Skips"]

_FAILED = _GOOD.replace(
    '<testcase name="AlsoPasses" status="run" result="completed" classname="Suite">',
    '<testcase name="AlsoPasses" status="run" result="completed" classname="Suite"><failure message="boom"/>',
)

_COUNT_MISMATCH = _GOOD.replace('<testsuites tests="3"', '<testsuites tests="4"')

_SKIPPED_WITH_LINK = _GOOD.replace(
    '<skipped message="later"/>',
    '<properties><property name="FullyVerifies" value="comp_req__y"/></properties><skipped message="later"/>',
)

_SKIPPED_WITH_CODE_LINK = _GOOD.replace(
    '<skipped message="later"/>',
    '<properties><property name="Verifies" value="::a::B()"/></properties><skipped message="later"/>',
)

_ERROR_ELEMENT = _GOOD.replace(
    '<testcase name="AlsoPasses" status="run" result="completed" classname="Suite">',
    '<testcase name="AlsoPasses" status="run" result="completed" classname="Suite"><error message="crash"/>',
)

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

_DUPLICATE = _GOOD.replace('name="AlsoPasses"', 'name="Passes"')

# As written by GoogleTest 1.17 for failures in SetUpTestSuite() of two suites
# and in a global Environment: nameless test cases that are not listed.
_SUITE_LEVEL = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites tests="2" failures="0" disabled="0" errors="0" name="AllTests">
  <testsuite name="A" tests="1">
    <testcase name="Body" status="run" result="skipped" classname="A"><skipped message=""/></testcase>
    <testcase name="" status="run" result="completed" classname=""><failure message="SetUpTestSuite"/></testcase>
  </testsuite>
  <testsuite name="B" tests="1">
    <testcase name="Body" status="run" result="completed" classname="B"/>
    <testcase name="" status="run" result="completed" classname=""><failure message="TearDownTestSuite"/></testcase>
  </testsuite>
  <testsuite name="NonTestSuiteFailure" tests="1" failures="1">
    <testcase name="" status="run" result="completed" classname=""><failure message="Environment"/></testcase>
  </testsuite>
</testsuites>
"""


def _shard(keys):
    cases = "".join(
        f'<testcase name="{k.split(".")[1]}" status="run" result="completed" classname="{k.split(".")[0]}"/>'
        for k in keys
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><testsuites tests="{len(keys)}" name="AllTests">'
        f'<testsuite name="Suite" tests="{len(keys)}">{cases}</testsuite></testsuites>'
    )


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
        results = gtest_report.parse_report(self._write(_FAILED))
        self.assertEqual(results["Suite.Passes"].result, "passed")
        self.assertEqual(results["Suite.AlsoPasses"].result, "failed")
        self.assertEqual(results["Suite.Skips"].result, "skipped")
        self.assertEqual(results["Suite.Passes"].properties, {"PartiallyVerifies": "comp_req__x"})

    def test_notrun_is_disabled(self):
        xml = _GOOD.replace('name="Passes" file="a.cpp" line="1" status="run"', 'name="Passes" status="notrun"')
        self.assertEqual(gtest_report.parse_report(self._write(xml))["Suite.Passes"].result, "disabled")

    def test_error_element_is_failed(self):
        results = gtest_report.parse_report(self._write(_ERROR_ELEMENT))
        self.assertEqual(results["Suite.AlsoPasses"].result, "failed")

    def test_property_attributes_of_old_gtest_versions(self):
        xml = _GOOD.replace('classname="Suite">\n      <properties>', 'classname="Suite" ASIL="B">\n      <properties>', 1)
        self.assertEqual(gtest_report.parse_report(self._write(xml))["Suite.Passes"].properties["ASIL"], "B")

    def test_duplicate_testcase_is_rejected(self):
        with self.assertRaises(ValueError):
            gtest_report.parse_report(self._write(_DUPLICATE))

    def test_suite_level_entries_are_keyed_per_suite(self):
        results = gtest_report.parse_report(self._write(_SUITE_LEVEL))
        self.assertEqual(
            sorted(k for k in results if gtest_report.is_suite_level(k)),
            ["A.(suite-level)", "B.(suite-level)", "NonTestSuiteFailure.(suite-level)"],
        )
        self.assertEqual(results["A.(suite-level)"].result, "failed")
        self.assertEqual(results["A.Body"].result, "skipped")

    def test_single_testsuite_root(self):
        xml = '<testsuite name="S" tests="1"><testcase name="T" classname="S"/></testsuite>'
        self.assertEqual(list(gtest_report.parse_report(self._write(xml))), ["S.T"])

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
        self.logs = Path(self._tmp.name) / "testlogs"
        self.bin = Path(self._tmp.name) / "bin"
        self.logs.mkdir()
        self.bin.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _report(self, content, target="pkg/unit_test", name="test.xml"):
        path = self.logs / target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _binary(self, keys, target="pkg/unit_test", exit_code=0):
        """Fake GoogleTest binary that lists the given test keys."""
        lines = ["Running main() from gmock_main.cc"]
        suite = None
        for key in keys:
            this_suite, name = key.split(".", 1)
            if this_suite != suite:
                lines.append(f"{this_suite}.")
                suite = this_suite
            lines.append(f"  {name}")
        output = "\n".join(lines) + "\n"
        script = Path(self._tmp.name) / f"fake_{target.replace('/', '_')}.py"
        script.write_text(f"import sys\nsys.stdout.write({output!r})\nsys.exit({exit_code})\n", encoding="utf-8")
        # A /bin/sh wrapper: the interpreter path under Bazel can exceed the
        # length limit of a #! line.
        path = self.bin / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def _check(self, expected_targets=None, **options):
        return check.check_testlogs(self.logs, check.Options(**options), expected_targets)

    @staticmethod
    def _messages(findings, severity="error"):
        return [f.message for f in findings if f.severity == severity]

    def test_consistent_report_has_no_errors(self):
        self._report(_GOOD)
        reports, findings = self._check()
        self.assertEqual(len(reports), 1)
        self.assertEqual(self._messages(findings), [])

    def test_missing_bazel_bin_is_a_warning(self):
        self._report(_GOOD)
        _, findings = self._check()
        self.assertTrue(any("--bazel-bin not given" in m for m in self._messages(findings, "warning")))

    def test_declared_count_mismatch_is_error(self):
        self._report(_COUNT_MISMATCH)
        _, findings = self._check()
        self.assertIn("report declares 4 tests but contains 3", self._messages(findings))

    def test_error_element_is_error(self):
        self._report(_ERROR_ELEMENT)
        _, findings = self._check()
        self.assertIn("Suite.AlsoPasses has an <error> element", self._messages(findings))

    def test_failed_test_case_is_error(self):
        self._report(_FAILED)
        _, findings = self._check()
        self.assertIn("Suite.AlsoPasses is reported as failed", self._messages(findings))

    def test_suite_level_failures_are_errors(self):
        self._report(_SUITE_LEVEL)
        _, findings = self._check()
        errors = self._messages(findings)
        for suite in ("A", "B", "NonTestSuiteFailure"):
            self.assertTrue(any(m.startswith(f"{suite}.(suite-level): failed outside a test case") for m in errors))

    def test_empty_gtest_report_is_error(self):
        self._report(_EMPTY_GTEST)
        _, findings = self._check()
        self.assertIn("GoogleTest report without test cases", self._messages(findings))

    def test_unreadable_report_is_error(self):
        self._report("<testsuites><testsuite>")
        _, findings = self._check()
        self.assertTrue(any(m.startswith("unreadable report") for m in self._messages(findings)))

    def test_non_gtest_report_is_warning_by_default(self):
        self._report(_BAZEL_FALLBACK, target="pkg/py_test")
        _, findings = self._check()
        self.assertEqual(self._messages(findings), [])
        self.assertIn("test.xml was not written by GoogleTest; not checked", self._messages(findings, "warning"))

    def test_non_gtest_report_can_be_error_or_ignored(self):
        self._report(_BAZEL_FALLBACK, target="pkg/py_test")
        _, findings = self._check(non_gtest="error")
        self.assertIn("test.xml was not written by GoogleTest; not checked", self._messages(findings))
        _, findings = self._check(non_gtest="ignore", bazel_bin=self.bin)
        self.assertEqual(findings, [])

    def test_skipped_with_requirement_link_is_warning_by_default(self):
        self._report(_SKIPPED_WITH_LINK)
        _, findings = self._check()
        self.assertEqual(self._messages(findings), [])
        self.assertIn("Suite.Skips is skipped but declares FullyVerifies", self._messages(findings, "warning"))

    def test_skipped_with_requirement_link_can_be_error(self):
        self._report(_SKIPPED_WITH_LINK)
        _, findings = self._check(fail_on_skipped_verification=True)
        self.assertIn("Suite.Skips is skipped but declares FullyVerifies", self._messages(findings))

    def test_skipped_with_code_link_is_only_a_warning(self):
        self._report(_SKIPPED_WITH_CODE_LINK)
        _, findings = self._check(fail_on_skipped_verification=True)
        self.assertEqual(self._messages(findings), [])
        self.assertIn("Suite.Skips is skipped but declares Verifies", self._messages(findings, "warning"))

    def test_shard_directory_maps_to_target(self):
        path = self._report(_GOOD, target="pkg/unit_test/shard_1_of_2")
        self.assertEqual(check._target_of(self.logs, path), "pkg/unit_test")

    # ------------------------------------------------ comparison with test list

    def test_list_matches_report(self):
        self._report(_GOOD)
        self._binary(_GOOD_KEYS)
        _, findings = self._check(bazel_bin=self.bin)
        self.assertEqual(findings, [])

    def test_listed_test_missing_from_report_is_error(self):
        self._report(_GOOD)
        self._binary(_GOOD_KEYS + ["Suite.Lost"])
        _, findings = self._check(bazel_bin=self.bin)
        self.assertIn("Suite.Lost listed by the binary but missing from the report", self._messages(findings))

    def test_reported_test_not_listed_is_error(self):
        self._report(_GOOD)
        self._binary(_GOOD_KEYS[:2])
        _, findings = self._check(bazel_bin=self.bin)
        self.assertIn("Suite.Skips reported but not listed by the binary", self._messages(findings))

    def test_missing_binary_is_error(self):
        self._report(_GOOD)
        _, findings = self._check(bazel_bin=self.bin)
        self.assertIn("test binary not found below --bazel-bin; test list not compared", self._messages(findings))

    def test_missing_binary_can_be_warning(self):
        self._report(_GOOD)
        _, findings = self._check(bazel_bin=self.bin, allow_missing_binary=True)
        self.assertEqual(self._messages(findings), [])

    def test_failing_test_list_is_error(self):
        self._report(_GOOD)
        self._binary(_GOOD_KEYS, exit_code=1)
        _, findings = self._check(bazel_bin=self.bin)
        self.assertTrue(any(m.startswith("could not list tests") for m in self._messages(findings)))

    def test_shards_are_merged_before_comparison(self):
        keys = ["Suite.A", "Suite.B", "Suite.C"]
        self._report(_shard(keys[:2]), target="pkg/unit_test/shard_1_of_2")
        self._report(_shard(keys[2:]), target="pkg/unit_test/shard_2_of_2")
        self._binary(keys)
        _, findings = self._check(bazel_bin=self.bin)
        self.assertEqual(findings, [])

    def test_missing_shard_is_detected(self):
        keys = ["Suite.A", "Suite.B", "Suite.C"]
        self._report(_shard(keys[:2]), target="pkg/unit_test/shard_1_of_2")
        self._binary(keys)
        _, findings = self._check(bazel_bin=self.bin)
        self.assertIn("Suite.C listed by the binary but missing from the report", self._messages(findings))

    def test_test_in_two_shards_is_error(self):
        keys = ["Suite.A", "Suite.B"]
        self._report(_shard(keys), target="pkg/unit_test/shard_1_of_2")
        self._report(_shard(keys[1:]), target="pkg/unit_test/shard_2_of_2")
        self._binary(keys)
        _, findings = self._check(bazel_bin=self.bin)
        self.assertIn("Suite.B is reported by more than one shard", self._messages(findings))

    # ---------------------------------------------------------- expected targets

    def test_expected_target_without_report_is_error(self):
        self._report(_GOOD)
        _, findings = self._check(expected_targets={"pkg/unit_test", "pkg/other_test"})
        self.assertEqual(
            [(f.target, f.message) for f in findings if f.severity == "error"],
            [("pkg/other_test", "expected test target has no test.xml (it did not run)")],
        )

    def test_unexpected_report_is_warning_and_not_checked(self):
        self._report(_GOOD)
        self._report(_FAILED, target="pkg/stale_test")
        _, findings = self._check(expected_targets={"pkg/unit_test"})
        self.assertEqual(self._messages(findings), [])
        self.assertIn(
            "report of a target that is not expected (stale?); not checked", self._messages(findings, "warning")
        )

    def test_target_of_label(self):
        self.assertEqual(check.target_of_label("//pkg/sub:name"), "pkg/sub/name")
        self.assertEqual(check.target_of_label("@@//pkg/sub:name"), "pkg/sub/name")
        self.assertEqual(check.target_of_label("//pkg/sub"), "pkg/sub/sub")
        with self.assertRaises(ValueError):
            check.target_of_label("@other//pkg:name")

    def test_read_expected_targets(self):
        path = Path(self._tmp.name) / "expected.txt"
        path.write_text("# comment\n//a:b\n\n@@//c/d:e  # trailing\n", encoding="utf-8")
        self.assertEqual(check.read_expected_targets(path), {"a/b", "c/d/e"})

    # ------------------------------------------------------------------ retries

    def test_retried_target_is_warning_by_default(self):
        self._report(_GOOD)
        (self.logs / "pkg/unit_test/test_attempts").mkdir()
        _, findings = self._check()
        self.assertEqual(self._messages(findings), [])
        self.assertTrue(any("more than one attempt" in m for m in self._messages(findings, "warning")))

    def test_retried_target_can_be_error(self):
        self._report(_GOOD)
        (self.logs / "pkg/unit_test/test_attempts").mkdir()
        _, findings = self._check(fail_on_retried_tests=True)
        self.assertTrue(any("more than one attempt" in m for m in self._messages(findings)))

    # --------------------------------------------------------------------- main

    def test_main_without_reports_fails(self):
        self.assertEqual(check.main(["--testlogs", str(self.logs)]), 1)

    def test_main_with_clean_report_passes(self):
        self._report(_GOOD)
        self._binary(_GOOD_KEYS)
        self.assertEqual(check.main(["--testlogs", str(self.logs), "--bazel-bin", str(self.bin)]), 0)

    def test_main_with_empty_expected_targets_fails(self):
        self._report(_GOOD)
        path = Path(self._tmp.name) / "expected.txt"
        path.write_text("# nothing\n", encoding="utf-8")
        self.assertEqual(check.main(["--testlogs", str(self.logs), "--expected-targets", str(path)]), 1)


if __name__ == "__main__":
    unittest.main()
