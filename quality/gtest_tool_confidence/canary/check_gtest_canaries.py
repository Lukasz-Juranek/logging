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
* that every listed test case is present in the XML report and vice versa,
* the reported result of every test case (passed/failed/skipped/disabled),
* required and forbidden RecordProperty() values.

GoogleTest is not used to judge itself: this checker is plain Python and reads
the XML report the same way docs-as-code does. A canary with a wrong result is
a detected malfunction of GoogleTest in this configuration.

Evidence (one line per canary, grouped by tool requirement) is written to
$TEST_UNDECLARED_OUTPUTS_DIR/gtest_canary_evidence.md when run under Bazel.
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


def _check_binary(name):
    spec = _EXPECTATIONS["binaries"][name]
    binary = _BINARIES[name]
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        xml_path = Path(tmp) / "report.xml"
        exit_code = gtest_report.run_with_report(binary, xml_path)
        exit_ok = (exit_code != 0) if spec["exit_code"] == "nonzero" else (exit_code == 0)
        if not exit_ok:
            problems.append(f"{name}: exit code {exit_code}, expected {spec['exit_code']}")
        _EVIDENCE.append(
            (spec["tool_req"], f"{name} (binary)", f"exit code {exit_code}", "ok" if exit_ok else "MISMATCH")
        )
        if not xml_path.exists():
            return problems + [f"{name}: no XML report written"]
        reported = gtest_report.parse_report(xml_path)

    listed = set(gtest_report.list_tests(binary))
    expected = set(spec["testcases"])
    for key in sorted(listed - set(reported)):
        problems.append(f"{name}: {key} listed but missing from the XML report")
    for key in sorted(set(reported) - listed):
        problems.append(f"{name}: {key} in the XML report but not listed")
    for key in sorted(listed - expected):
        problems.append(f"{name}: {key} has no expectation (add it to canary_expectations.json)")
    for key in sorted(expected - listed):
        problems.append(f"{name}: expected canary {key} does not exist in the binary")

    for key in sorted(expected & set(reported)):
        want = spec["testcases"][key]
        got = reported[key]
        ok = got.result == want["result"]
        if not ok:
            problems.append(f"{name}: {key} reported '{got.result}', expected '{want['result']}'")
        for prop, value in want.get("required_properties", {}).items():
            if got.properties.get(prop) != value:
                ok = False
                problems.append(
                    f"{name}: {key} property {prop}={got.properties.get(prop)!r}, expected {value!r}"
                )
        for prop in want.get("forbidden_properties", []):
            if prop in got.properties:
                ok = False
                problems.append(f"{name}: {key} must not report property {prop}")
        _EVIDENCE.append((want["tool_req"], key, got.result, "ok" if ok else "MISMATCH"))
    return problems


def _check_premature_exit():
    """A test calling exit(0) must leave TEST_PREMATURE_EXIT_FILE behind."""
    spec = _EXPECTATIONS["binaries"]["premature_exit"]
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / "premature_exit"
        exit_code = gtest_report.run_with_report(
            _BINARIES["premature_exit"],
            Path(tmp) / "report.xml",
            extra_env={"TEST_PREMATURE_EXIT_FILE": str(marker)},
        )
        if spec["exit_code"] == "zero" and exit_code != 0:
            problems.append(f"premature_exit: exit code {exit_code}, expected 0 (canary assumption broken)")
        left_behind = marker.exists()
        if spec["premature_exit_file"] == "present" and not left_behind:
            problems.append("premature_exit: TEST_PREMATURE_EXIT_FILE was removed; Bazel would report a pass")
        _EVIDENCE.append(
            (
                spec["tool_req"],
                "CanaryPrematureExit.ExitZeroInsideTest",
                "exit file left behind" if left_behind else "exit file removed",
                "ok" if not problems else "MISMATCH",
            )
        )
    return problems


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

    def test_must_fail_canaries_are_reported_as_failed(self):
        problems = _check_binary("must_fail")
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_must_pass_canaries_are_reported_correctly(self):
        problems = _check_binary("must_pass")
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_premature_exit_is_detectable(self):
        problems = _check_premature_exit()
        self.assertEqual(problems, [], "\n" + "\n".join(problems))


def main(argv):
    global _EXPECTATIONS
    if len(argv) != 5:
        sys.exit(
            f"usage: {argv[0]} <expectations.json> <must_fail binary> <must_pass binary> <premature_exit binary>"
        )
    _EXPECTATIONS = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    _BINARIES["must_fail"] = Path(argv[2]).resolve()
    _BINARIES["must_pass"] = Path(argv[3]).resolve()
    _BINARIES["premature_exit"] = Path(argv[4]).resolve()
    unittest.main(argv=argv[:1], verbosity=2)


if __name__ == "__main__":
    main(sys.argv)
