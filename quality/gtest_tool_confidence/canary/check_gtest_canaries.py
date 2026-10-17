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
"""Independent checker for the GoogleTest canaries.

Runs each canary binary with the toolchain and flags of the current build
configuration and verifies, against canary_expectations.json:

* the process exit code (failing binary -> non-zero, passing binary -> zero),
* the premature-exit marker (TEST_PREMATURE_EXIT_FILE): removed on a normal
  end, left behind after exit(0) inside a test,
* that every test case listed by --gtest_list_tests is present in the XML
  report and vice versa; entries the binary does not list (failures outside a
  test case) must be expected explicitly,
* the reported result of every test case (passed/failed/skipped/disabled),
* the RecordProperty() values: required values must be present, forbidden ones
  absent, and no test case may report a property that it did not record
  (a property attached to the wrong test case).

GoogleTest is not used to judge itself: this checker is plain Python and reads
the XML report the same way docs-as-code does. A canary with a wrong result is
a detected malfunction of GoogleTest in this configuration.

Evidence (one line per canary, grouped by tool requirement) is written to
$TEST_UNDECLARED_OUTPUTS_DIR/gtest_canary_evidence.md when run under Bazel.

Usage: check_gtest_canaries.py <expectations.json> <name>=<binary> ...
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from quality.gtest_tool_confidence.common import gtest_report

_EXPECTATIONS = None
_BINARIES = {}
_EVIDENCE = []


def _verdict(ok):
    return "ok" if ok else "MISMATCH"


def _check_testcase(name, key, want, got):
    """Compare one reported test case with its expectation."""
    problems = []
    if got.result != want["result"]:
        problems.append(f"{name}: {key} reported '{got.result}', expected '{want['result']}'")
    required = want.get("required_properties", {})
    for prop, value in required.items():
        if got.properties.get(prop) != value:
            problems.append(f"{name}: {key} property {prop}={got.properties.get(prop)!r}, expected {value!r}")
    for prop in want.get("forbidden_properties", []):
        if prop in got.properties:
            problems.append(f"{name}: {key} must not report property {prop}")
    for prop in sorted(set(got.properties) - set(required) - set(want.get("forbidden_properties", []))):
        problems.append(f"{name}: {key} reports property {prop} that it did not record")
    return problems


def check_binary(name, spec, binary):
    """Run one canary binary and compare it with its expectation.

    Returns (problems, evidence); evidence rows are (tool_req, canary, reported, verdict).
    """
    problems = []
    evidence = []
    listed = gtest_report.list_tests(binary)
    with tempfile.TemporaryDirectory() as tmp:
        xml_path = Path(tmp) / "report.xml"
        marker = Path(tmp) / "premature_exit"
        exit_code = gtest_report.run_with_report(
            binary, xml_path, cwd=tmp, extra_env={"TEST_PREMATURE_EXIT_FILE": str(marker)}
        )
        reported = gtest_report.parse_report(xml_path) if xml_path.exists() else None
        marker_left = marker.exists()

    want_exit = spec["exit_code"]
    exit_ok = (exit_code != 0) if want_exit == "nonzero" else (exit_code == 0)
    if not exit_ok:
        problems.append(f"{name}: exit code {exit_code}, expected {want_exit}")
    evidence.append((spec["tool_req"], f"{name} (binary)", f"exit code {exit_code}", _verdict(exit_ok)))

    want_marker = spec.get("premature_exit_file", "absent")
    marker_ok = marker_left == (want_marker == "present")
    if not marker_ok:
        state = "left behind" if marker_left else "removed"
        problems.append(f"{name}: TEST_PREMATURE_EXIT_FILE was {state}, expected {want_marker}")
    evidence.append(
        (
            spec["tool_req"],
            f"{name} (premature-exit marker)",
            "left behind" if marker_left else "removed",
            _verdict(marker_ok),
        )
    )

    expected = spec["testcases"]
    for key in sorted(set(listed) - set(expected)):
        problems.append(f"{name}: {key} has no expectation (add it to canary_expectations.json)")
    for key in sorted(set(expected) - set(listed)):
        problems.append(f"{name}: expected canary {key} is not listed by the binary")

    if spec.get("report") == "incomplete":
        # The binary ends before the report is complete (premature exit): the
        # report must be missing or lack listed test cases, so that the
        # completeness check (M2) can detect the incomplete run.
        missing = set(listed) - set(reported or {})
        incomplete = reported is None or bool(missing)
        if not incomplete:
            problems.append(f"{name}: report is complete although the binary ended prematurely")
        evidence.append(
            (
                spec["tool_req"],
                f"{name} (report)",
                "no report" if reported is None else f"{len(missing)} listed test(s) missing",
                _verdict(incomplete),
            )
        )
        return problems, evidence

    if reported is None:
        return problems + [f"{name}: no XML report written"], evidence

    unlisted = spec.get("unlisted_entries", {})
    for key in sorted(set(listed) - set(reported)):
        problems.append(f"{name}: {key} listed but missing from the XML report")
    for key in sorted(set(reported) - set(listed) - set(unlisted)):
        problems.append(f"{name}: {key} in the XML report but not listed")
    for key in sorted(set(unlisted) - set(reported)):
        problems.append(f"{name}: expected unlisted entry {key} is missing from the XML report")

    for key in sorted(set(reported) & (set(expected) | set(unlisted))):
        want = expected.get(key) or unlisted[key]
        case_problems = _check_testcase(name, key, want, reported[key])
        problems.extend(case_problems)
        evidence.append((want["tool_req"], key, reported[key].result, _verdict(not case_problems)))
    return problems, evidence


def _write_evidence():
    out_dir = os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR")
    if not out_dir:
        return
    lines = ["| tool_req | canary | reported | verdict |", "|---|---|---|---|"]
    for tool_req, canary, reported, verdict in sorted(_EVIDENCE):
        lines.append(f"| {tool_req} | {canary} | {reported} | {verdict} |")
    Path(out_dir, "gtest_canary_evidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


class GtestCanaryTest(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        _write_evidence()

    def test_every_expected_binary_is_given(self):
        self.assertEqual(sorted(_BINARIES), sorted(_EXPECTATIONS["binaries"]))

    def test_canaries(self):
        for name in sorted(_EXPECTATIONS["binaries"]):
            with self.subTest(binary=name):
                if name not in _BINARIES:
                    self.fail(f"{name}: binary not given")
                problems, evidence = check_binary(name, _EXPECTATIONS["binaries"][name], _BINARIES[name])
                _EVIDENCE.extend(evidence)
                self.assertEqual(problems, [], "\n" + "\n".join(problems))


def parse_args(argv):
    """Return (expectations, {name: binary}) from the command line."""
    if len(argv) < 3:
        raise SystemExit(f"usage: {argv[0]} <expectations.json> <name>=<binary> ...")
    binaries = {}
    for arg in argv[2:]:
        name, sep, path = arg.partition("=")
        if not sep or not name or not path:
            raise SystemExit(f"expected <name>=<binary>, got {arg!r}")
        binaries[name] = Path(path).resolve()
    expectations = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    return expectations, binaries


def main(argv):
    global _EXPECTATIONS
    _EXPECTATIONS, binaries = parse_args(argv)
    _BINARIES.clear()
    _BINARIES.update(binaries)
    unittest.main(argv=argv[:1], verbosity=2)


if __name__ == "__main__":
    main(sys.argv)
