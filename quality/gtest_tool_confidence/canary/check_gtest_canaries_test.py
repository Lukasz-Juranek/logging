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
"""Unit tests for the canary checker.

The checker is the independent judge of GoogleTest, so it must itself be shown
to FAIL whenever a (simulated) GoogleTest reports a wrong result. The fake
binaries below behave like a GoogleTest binary (--gtest_list_tests,
--gtest_output=xml:..., TEST_PREMATURE_EXIT_FILE, exit code) with configurable
defects.
"""

import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from xml.sax.saxutils import quoteattr

from quality.gtest_tool_confidence.canary import check_gtest_canaries as checker

_FAKE_BINARY = """import json
import os
import sys

CFG = json.loads({config!r})
if "--gtest_list_tests" in sys.argv:
    sys.stdout.write(CFG["list"])
    sys.exit(0)
marker = os.environ.get("TEST_PREMATURE_EXIT_FILE")
if marker:
    open(marker, "w").close()
for arg in sys.argv[1:]:
    if arg.startswith("--gtest_output=xml:") and CFG["xml"] is not None:
        with open(arg[len("--gtest_output=xml:"):], "w") as report:
            report.write(CFG["xml"])
if marker and not CFG["keep_marker"]:
    os.remove(marker)
sys.exit(CFG["exit"])
"""


def _testcase_xml(key, result, properties):
    suite, name = key.split(".", 1)
    if name == "(suite-level)":
        suite, name = "", ""
    status = "notrun" if result == "disabled" else "run"
    body = ""
    if properties:
        body += "<properties>"
        body += "".join(f"<property name={quoteattr(k)} value={quoteattr(v)}/>" for k, v in properties.items())
        body += "</properties>"
    if result == "failed":
        body += '<failure message="canary" type=""/>'
    elif result == "skipped":
        body += '<skipped message="canary"/>'
    return f'<testcase name={quoteattr(name)} status="{status}" classname={quoteattr(suite)}>{body}</testcase>'


def make_report(cases):
    """cases: {key: (result, {property: value})} -> GoogleTest-like XML report."""
    suites = {}
    for key, (result, properties) in cases.items():
        suites.setdefault(key.split(".", 1)[0], []).append(_testcase_xml(key, result, properties))
    body = "".join(
        f'<testsuite name={quoteattr(name)} tests="{len(tcs)}">{"".join(tcs)}</testsuite>'
        for name, tcs in suites.items()
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><testsuites tests="{len(cases)}" name="AllTests">{body}</testsuites>'


def make_executable(path, script):
    """Wrap a Python script into an executable.

    A /bin/sh wrapper is used because the interpreter path under Bazel can
    exceed the length limit of a #! line.
    """
    path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def make_list(keys):
    """Keys -> --gtest_list_tests output, including the gtest_main banner."""
    lines = ["Running main() from gmock_main.cc"]
    suite = None
    for key in keys:
        this_suite, name = key.split(".", 1)
        if this_suite != suite:
            lines.append(f"{this_suite}.")
            suite = this_suite
        lines.append(f"  {name}")
    return "\n".join(lines) + "\n"


# A correct GoogleTest for SPEC: every expectation is met.
SPEC = {
    "exit_code": "nonzero",
    "tool_req": "tool_req__exit",
    "testcases": {
        "Suite.MustFail": {"result": "failed", "tool_req": "tool_req__a"},
        "Suite.MustPass": {
            "result": "passed",
            "tool_req": "tool_req__b",
            "required_properties": {"FullyVerifies": "req__x"},
        },
        "Suite.StopsAfterAssert": {
            "result": "failed",
            "tool_req": "tool_req__c",
            "forbidden_properties": ["Reached"],
        },
        "Suite.Skipped": {"result": "skipped", "tool_req": "tool_req__d"},
        "Suite.DISABLED_Off": {"result": "disabled", "tool_req": "tool_req__d"},
    },
}
GOOD_CASES = {
    "Suite.MustFail": ("failed", {}),
    "Suite.MustPass": ("passed", {"FullyVerifies": "req__x"}),
    "Suite.StopsAfterAssert": ("failed", {}),
    "Suite.Skipped": ("skipped", {}),
    "Suite.DISABLED_Off": ("disabled", {}),
}


class CheckerTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self._count = 0

    def tearDown(self):
        self._tmp.cleanup()

    def fake(self, cases=None, listed=None, exit_code=1, xml="default", keep_marker=False):
        """Create a fake GoogleTest binary and return its path."""
        cases = dict(GOOD_CASES) if cases is None else cases
        listed = [k for k in cases if not k.endswith(".(suite-level)")] if listed is None else listed
        config = {
            "list": make_list(listed),
            "xml": make_report(cases) if xml == "default" else xml,
            "exit": exit_code,
            "keep_marker": keep_marker,
        }
        self._count += 1
        script = self.dir / f"fake_gtest_{self._count}.py"
        script.write_text(_FAKE_BINARY.format(config=json.dumps(config)), encoding="utf-8")
        return make_executable(self.dir / f"fake_gtest_{self._count}", script)

    def problems(self, binary, spec=None):
        problems, _ = checker.check_binary("fake", spec or SPEC, binary)
        return problems

    def assertDetected(self, binary, fragment, spec=None):
        problems = self.problems(binary, spec)
        self.assertTrue(
            any(fragment in p for p in problems), f"checker did not report {fragment!r}; problems: {problems}"
        )


class CorrectGoogleTestTest(CheckerTestBase):
    def test_correct_results_pass(self):
        self.assertEqual(self.problems(self.fake()), [])

    def test_evidence_has_one_row_per_canary(self):
        _, evidence = checker.check_binary("fake", SPEC, self.fake())
        canaries = [row[1] for row in evidence]
        self.assertEqual(len(canaries), len(SPEC["testcases"]) + 2)
        self.assertTrue(all(row[3] == "ok" for row in evidence))


class WrongResultsAreDetectedTest(CheckerTestBase):
    """Each test simulates one GoogleTest malfunction; the checker must fail."""

    def _with(self, key, result, properties=None):
        cases = dict(GOOD_CASES)
        cases[key] = (result, properties if properties is not None else cases[key][1])
        return cases

    def test_false_pass(self):
        self.assertDetected(self.fake(self._with("Suite.MustFail", "passed")), "Suite.MustFail reported 'passed'")

    def test_false_failure(self):
        self.assertDetected(self.fake(self._with("Suite.MustPass", "failed")), "Suite.MustPass reported 'failed'")

    def test_skipped_reported_as_passed(self):
        self.assertDetected(self.fake(self._with("Suite.Skipped", "passed")), "Suite.Skipped reported 'passed'")

    def test_disabled_reported_as_passed(self):
        self.assertDetected(
            self.fake(self._with("Suite.DISABLED_Off", "passed")), "Suite.DISABLED_Off reported 'passed'"
        )

    def test_exit_code_zero_despite_failures(self):
        self.assertDetected(self.fake(exit_code=0), "exit code 0, expected nonzero")

    def test_exit_code_nonzero_for_passing_binary(self):
        spec = dict(SPEC, exit_code="zero")
        self.assertDetected(self.fake(exit_code=1), "exit code 1, expected zero", spec)

    def test_listed_test_missing_from_report(self):
        cases = dict(GOOD_CASES)
        del cases["Suite.Skipped"]
        self.assertDetected(self.fake(cases, listed=list(GOOD_CASES)), "Suite.Skipped listed but missing")

    def test_reported_test_not_listed(self):
        listed = [k for k in GOOD_CASES if k != "Suite.Skipped"]
        self.assertDetected(self.fake(listed=listed), "Suite.Skipped in the XML report but not listed")

    def test_unexpected_test_case(self):
        cases = dict(GOOD_CASES, **{"Suite.Extra": ("passed", {})})
        self.assertDetected(self.fake(cases), "Suite.Extra has no expectation")

    def test_expected_canary_missing_from_binary(self):
        cases = dict(GOOD_CASES)
        del cases["Suite.Skipped"]
        self.assertDetected(self.fake(cases), "expected canary Suite.Skipped is not listed")

    def test_required_property_lost(self):
        self.assertDetected(self.fake(self._with("Suite.MustPass", "passed", {})), "property FullyVerifies=None")

    def test_required_property_changed(self):
        cases = self._with("Suite.MustPass", "passed", {"FullyVerifies": "req__"})
        self.assertDetected(self.fake(cases), "property FullyVerifies='req__'")

    def test_property_attached_to_wrong_test_case(self):
        cases = self._with("Suite.MustPass", "passed", {})
        cases["Suite.MustFail"] = ("failed", {"FullyVerifies": "req__x"})
        self.assertDetected(self.fake(cases), "Suite.MustFail reports property FullyVerifies that it did not record")

    def test_property_recorded_after_fatal_failure(self):
        cases = self._with("Suite.StopsAfterAssert", "failed", {"Reached": "yes"})
        self.assertDetected(self.fake(cases), "Suite.StopsAfterAssert must not report property Reached")

    def test_no_report(self):
        self.assertDetected(self.fake(xml=None), "no XML report written")

    def test_duplicate_test_case_is_rejected(self):
        xml = make_report(GOOD_CASES).replace('name="MustPass"', 'name="MustFail"')
        with self.assertRaises(ValueError):
            self.problems(self.fake(xml=xml))

    def test_marker_left_behind_on_normal_end(self):
        self.assertDetected(self.fake(keep_marker=True), "TEST_PREMATURE_EXIT_FILE was left behind")


class SuiteLevelAndPrematureExitTest(CheckerTestBase):
    UNLISTED_SPEC = dict(
        SPEC,
        unlisted_entries={"Suite.(suite-level)": {"result": "failed", "tool_req": "tool_req__f"}},
    )

    def test_expected_suite_level_failure_passes(self):
        cases = dict(GOOD_CASES, **{"Suite.(suite-level)": ("failed", {})})
        self.assertEqual(self.problems(self.fake(cases), self.UNLISTED_SPEC), [])

    def test_missing_suite_level_failure_is_detected(self):
        self.assertDetected(self.fake(), "expected unlisted entry Suite.(suite-level) is missing", self.UNLISTED_SPEC)

    def test_suite_level_entry_reported_as_passed_is_detected(self):
        cases = dict(GOOD_CASES, **{"Suite.(suite-level)": ("passed", {})})
        self.assertDetected(self.fake(cases), "Suite.(suite-level) reported 'passed'", self.UNLISTED_SPEC)

    def test_unexpected_suite_level_entry_is_detected(self):
        cases = dict(GOOD_CASES, **{"Suite.(suite-level)": ("failed", {})})
        self.assertDetected(self.fake(cases), "Suite.(suite-level) in the XML report but not listed")

    PREMATURE_SPEC = {
        "exit_code": "zero",
        "premature_exit_file": "present",
        "report": "incomplete",
        "tool_req": "tool_req__complete",
        "testcases": {
            "Exit.First": {"result": "not reported", "tool_req": "tool_req__complete"},
            "Exit.Second": {"result": "not reported", "tool_req": "tool_req__complete"},
        },
    }
    PREMATURE_CASES = {"Exit.First": ("passed", {}), "Exit.Second": ("passed", {})}

    def test_premature_exit_detected_correctly(self):
        binary = self.fake(self.PREMATURE_CASES, exit_code=0, xml=None, keep_marker=True)
        self.assertEqual(self.problems(binary, self.PREMATURE_SPEC), [])

    def test_premature_exit_with_partial_report_is_accepted(self):
        binary = self.fake({"Exit.First": ("passed", {})}, listed=list(self.PREMATURE_CASES), exit_code=0, keep_marker=True)
        self.assertEqual(self.problems(binary, self.PREMATURE_SPEC), [])

    def test_premature_exit_marker_removed_is_detected(self):
        binary = self.fake(self.PREMATURE_CASES, exit_code=0, xml=None, keep_marker=False)
        self.assertDetected(binary, "TEST_PREMATURE_EXIT_FILE was removed", self.PREMATURE_SPEC)

    def test_premature_exit_with_complete_report_is_detected(self):
        binary = self.fake(self.PREMATURE_CASES, exit_code=0, keep_marker=True)
        self.assertDetected(binary, "report is complete although the binary ended prematurely", self.PREMATURE_SPEC)


class ArgumentsAndExpectationsTest(unittest.TestCase):
    def test_parse_args(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "e.json"
            path.write_text('{"binaries": {}}', encoding="utf-8")
            expectations, binaries = checker.parse_args(["prog", str(path), "a=/bin/a", "b=/bin/b"])
        self.assertEqual(expectations, {"binaries": {}})
        self.assertEqual(sorted(binaries), ["a", "b"])

    def test_parse_args_rejects_malformed_binary(self):
        with self.assertRaises(SystemExit):
            checker.parse_args(["prog", "e.json", "/bin/a"])

    def test_expectations_file_is_well_formed(self):
        path = Path(__file__).with_name("canary_expectations.json")
        expectations = json.loads(path.read_text(encoding="utf-8"))
        results = {"passed", "failed", "skipped", "disabled", "not reported"}
        for name, spec in expectations["binaries"].items():
            self.assertIn(spec["exit_code"], ("zero", "nonzero"), name)
            self.assertTrue(spec["tool_req"].startswith("tool_req__gtest_"), name)
            entries = dict(spec["testcases"], **spec.get("unlisted_entries", {}))
            self.assertTrue(entries, name)
            for key, want in entries.items():
                self.assertIn(want["result"], results, key)
                self.assertTrue(want["tool_req"].startswith("tool_req__gtest_"), key)


if __name__ == "__main__":
    unittest.main()
