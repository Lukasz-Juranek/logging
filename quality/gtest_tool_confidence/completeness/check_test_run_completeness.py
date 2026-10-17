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
"""Check that a Bazel test run produced complete and consistent GoogleTest reports.

Run after ``bazel test``. For every ``test.xml`` below the test logs directory:

* the report must be parseable,
* a GoogleTest report must contain at least one test case,
* the ``tests`` count declared by the report must equal the number of
  ``<testcase>`` elements,
* no test case may carry an ``<error>`` element,
* if the test binary is found below ``--bazel-bin``, every test it lists with
  ``--gtest_list_tests`` must be present in the report (lost results),
* skipped or disabled test cases that declare ``FullyVerifies`` /
  ``PartiallyVerifies`` / ``Verifies`` are reported, because they carry
  requirement links without verifying anything (an error with
  ``--fail-on-skipped-verification``).

Usage:
    bazel test --config=x86_64-linux //score/...
    bazel run //quality/gtest_tool_confidence/completeness:check_test_run_completeness -- \\
        --testlogs "$(bazel info --config=x86_64-linux bazel-testlogs)" \\
        --bazel-bin "$(bazel info --config=x86_64-linux bazel-bin)"

Exit code 0 if no errors were found, 1 otherwise.
"""

import argparse
import dataclasses
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from quality.gtest_tool_confidence.common import gtest_report

_VERIFYING_PROPERTIES = ("FullyVerifies", "PartiallyVerifies", "Verifies")


@dataclasses.dataclass
class Finding:
    severity: str  # "error" or "warning"
    target: str
    message: str


def _target_of(testlogs, xml_path):
    rel = xml_path.parent.relative_to(testlogs)
    parts = rel.parts
    if parts and parts[-1].startswith("shard_"):
        parts = parts[:-1]
    return "/".join(parts)


def _binary_of(bazel_bin, target):
    if bazel_bin is None:
        return None
    candidate = Path(bazel_bin) / target
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate
    return None


def _listed_tests(binary):
    runfiles = Path(f"{binary}.runfiles")
    cwd = runfiles / "_main" if (runfiles / "_main").is_dir() else binary.parent
    extra = {"RUNFILES_DIR": str(runfiles)} if runfiles.is_dir() else None
    return gtest_report.list_tests(binary, cwd=cwd, env=gtest_report.clean_test_env(extra))


def check_report(testlogs, xml_path, bazel_bin=None, fail_on_skipped_verification=False):
    target = _target_of(testlogs, xml_path)
    findings = []
    try:
        reported = gtest_report.parse_report(xml_path)
        declared = gtest_report.declared_test_count(xml_path)
        is_gtest = gtest_report.is_gtest_report(xml_path)
    except (ET.ParseError, ValueError) as error:
        return [Finding("error", target, f"unreadable report: {error}")]

    if not is_gtest:
        return findings
    if not reported:
        findings.append(Finding("error", target, "GoogleTest report without test cases"))
    if declared is not None and declared != len(reported):
        findings.append(
            Finding("error", target, f"report declares {declared} tests but contains {len(reported)}")
        )
    root = ET.parse(xml_path).getroot()
    for testcase in root.iter("testcase"):
        if testcase.find("error") is not None:
            findings.append(
                Finding("error", target, f"{gtest_report.testcase_key(testcase)} has an <error> element")
            )

    is_shard = xml_path.parent.name.startswith("shard_")
    binary = _binary_of(bazel_bin, target)
    if binary is not None and not is_shard:
        try:
            listed = _listed_tests(binary)
        except (RuntimeError, ValueError, OSError) as error:
            findings.append(Finding("warning", target, f"could not list tests: {error}"))
        else:
            for key in sorted(set(listed) - set(reported)):
                findings.append(Finding("error", target, f"{key} listed by the binary but missing from the report"))

    severity = "error" if fail_on_skipped_verification else "warning"
    for key, result in sorted(reported.items()):
        if result.result in ("skipped", "disabled"):
            links = [p for p in _VERIFYING_PROPERTIES if result.properties.get(p)]
            if links:
                findings.append(
                    Finding(severity, target, f"{key} is {result.result} but declares {', '.join(links)}")
                )
    return findings


def check_testlogs(testlogs, bazel_bin=None, fail_on_skipped_verification=False):
    testlogs = Path(testlogs)
    reports = sorted(testlogs.rglob("test.xml"))
    findings = []
    for xml_path in reports:
        findings.extend(check_report(testlogs, xml_path, bazel_bin, fail_on_skipped_verification))
    return reports, findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--testlogs", required=True, help="Bazel test logs directory (bazel info bazel-testlogs)")
    parser.add_argument("--bazel-bin", help="Bazel output directory (bazel info bazel-bin); enables list comparison")
    parser.add_argument(
        "--fail-on-skipped-verification",
        action="store_true",
        help="treat skipped/disabled tests with requirement links as errors",
    )
    args = parser.parse_args(argv)

    if not Path(args.testlogs).is_dir():
        print(f"error: {args.testlogs} is not a directory", file=sys.stderr)
        return 1
    reports, findings = check_testlogs(args.testlogs, args.bazel_bin, args.fail_on_skipped_verification)
    for finding in findings:
        print(f"{finding.severity.upper()}: //{finding.target}: {finding.message}")
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = len(findings) - errors
    print(f"checked {len(reports)} report(s): {errors} error(s), {warnings} warning(s)")
    if not reports:
        print("error: no test.xml found", file=sys.stderr)
        return 1
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
