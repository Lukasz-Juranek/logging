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

Run after a successful ``bazel test``. Checks per test target (the ``test.xml``
files of all shards of a target are merged):

* with ``--expected-targets``: every expected test target has a report (a
  target that did not run is an error); reports of other targets are reported
  as warnings (stale or out of scope) and not checked further,
* every report is parseable; a report not written by GoogleTest (Bazel's
  fallback report, other test frameworks) is a warning (``--non-gtest``),
* a GoogleTest target reports at least one test case, and the ``tests`` count
  declared by each report equals its number of ``<testcase>`` elements,
* no test case carries an ``<error>`` element and no test case is reported as
  failed (the run passed, so a failed test case means the exit code did not
  reflect it),
* no failure outside a test case (``SetUpTestSuite()``,
  ``TearDownTestSuite()``, a global ``Environment``) is reported,
* with ``--bazel-bin``: the tests listed by the binary
  (``--gtest_list_tests``) and the reported tests are identical in both
  directions. This detects lost results and runs restricted by a filter. A
  missing binary or a failing list is an error (``--allow-missing-binary``
  turns a missing binary into a warning),
* a target that needed more than one attempt (``flaky_test_attempts``) is a
  warning, or an error with ``--fail-on-retried-tests``,
* skipped or disabled test cases that declare ``FullyVerifies`` /
  ``PartiallyVerifies`` are warnings, or errors with
  ``--fail-on-skipped-verification``; a skipped test case with ``Verifies``
  (a code reference) is a warning.

Usage:
    bazel test --config=x86_64-linux //score/...
    bazel run //quality/gtest_tool_confidence/completeness:check_test_run_completeness -- \\
        --testlogs "$(bazel info --config=x86_64-linux bazel-testlogs)" \\
        --bazel-bin "$(bazel info --config=x86_64-linux bazel-bin)" \\
        --expected-targets expected_tests.txt --fail-on-skipped-verification

Exit code 0 if no errors were found, 1 otherwise.
"""

import argparse
import dataclasses
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from quality.gtest_tool_confidence.common import gtest_report

_REQUIREMENT_LINKS = ("FullyVerifies", "PartiallyVerifies")
_CODE_LINKS = ("Verifies",)


@dataclasses.dataclass
class Finding:
    severity: str  # "error" or "warning"
    target: str
    message: str


@dataclasses.dataclass
class Options:
    bazel_bin: Path = None
    fail_on_skipped_verification: bool = False
    fail_on_retried_tests: bool = False
    allow_missing_binary: bool = False
    non_gtest: str = "warn"  # "ignore", "warn" or "error"


def _target_of(testlogs, xml_path):
    rel = xml_path.parent.relative_to(testlogs)
    parts = rel.parts
    if parts and parts[-1].startswith("shard_"):
        parts = parts[:-1]
    return "/".join(parts)


def target_of_label(label):
    """Map a Bazel label of the main repository to its test logs path.

    "//pkg/sub:name", "@@//pkg/sub:name" and "//pkg/sub" (name = last package
    segment) map to "pkg/sub/name".
    """
    label = label.strip()
    for prefix in ("@@//", "@//", "//"):
        if label.startswith(prefix):
            label = label[len(prefix) :]
            break
    else:
        raise ValueError(f"not a label of the main repository: {label!r}")
    package, sep, name = label.partition(":")
    if not sep:
        name = package.rsplit("/", 1)[-1]
    return f"{package}/{name}" if package else name


def read_expected_targets(path):
    targets = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            targets.add(target_of_label(line))
    return targets


def _binary_of(bazel_bin, target):
    candidate = Path(bazel_bin) / target
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate
    return None


def _listed_tests(binary):
    runfiles = Path(f"{binary}.runfiles")
    cwd = runfiles / "_main" if (runfiles / "_main").is_dir() else binary.parent
    extra = {"RUNFILES_DIR": str(runfiles)} if runfiles.is_dir() else None
    return gtest_report.list_tests(binary, cwd=cwd, env=gtest_report.clean_test_env(extra))


def _compare_with_list(target, reported, options):
    findings = []
    binary = _binary_of(options.bazel_bin, target)
    if binary is None:
        severity = "warning" if options.allow_missing_binary else "error"
        return [Finding(severity, target, "test binary not found below --bazel-bin; test list not compared")]
    try:
        listed = set(_listed_tests(binary))
    except (RuntimeError, ValueError, OSError) as error:
        return [Finding("error", target, f"could not list tests: {error}")]
    for key in sorted(listed - set(reported)):
        findings.append(Finding("error", target, f"{key} listed by the binary but missing from the report"))
    for key in sorted(set(reported) - listed):
        if not gtest_report.is_suite_level(key):
            findings.append(Finding("error", target, f"{key} reported but not listed by the binary"))
    return findings


def check_target(target, xml_paths, options):
    """Check the report(s) of one test target (one per shard)."""
    findings = []
    if any((path.parent / "test_attempts").is_dir() for path in xml_paths):
        findings.append(
            Finding(
                "error" if options.fail_on_retried_tests else "warning",
                target,
                "target needed more than one attempt (flaky_test_attempts); a failed attempt is not visible "
                "in the final report",
            )
        )

    reported = {}
    for xml_path in sorted(xml_paths):
        try:
            if not gtest_report.is_gtest_report(xml_path):
                if options.non_gtest != "ignore":
                    findings.append(
                        Finding(
                            "error" if options.non_gtest == "error" else "warning",
                            target,
                            f"{xml_path.name} was not written by GoogleTest; not checked",
                        )
                    )
                return findings
            results = gtest_report.parse_report(xml_path)
            declared = gtest_report.declared_test_count(xml_path)
            root = ET.parse(xml_path).getroot()
        except (ET.ParseError, ValueError) as error:
            return findings + [Finding("error", target, f"unreadable report: {error}")]

        if declared is not None and declared != len(results):
            findings.append(
                Finding("error", target, f"report declares {declared} tests but contains {len(results)}")
            )
        for key, testcase in gtest_report.iter_testcases(root):
            if testcase.find("error") is not None:
                findings.append(Finding("error", target, f"{key} has an <error> element"))
        for key in sorted(set(results) & set(reported)):
            findings.append(Finding("error", target, f"{key} is reported by more than one shard"))
        reported.update(results)

    if not reported:
        findings.append(Finding("error", target, "GoogleTest report without test cases"))

    for key, result in sorted(reported.items()):
        if gtest_report.is_suite_level(key):
            findings.append(
                Finding(
                    "error",
                    target,
                    f"{key}: {result.result} outside a test case (SetUpTestSuite, TearDownTestSuite or a "
                    "global Environment)",
                )
            )
        elif result.result == "failed":
            findings.append(Finding("error", target, f"{key} is reported as failed"))

    if options.bazel_bin is not None:
        findings.extend(_compare_with_list(target, reported, options))

    for key, result in sorted(reported.items()):
        if result.result not in ("skipped", "disabled"):
            continue
        requirement_links = [p for p in _REQUIREMENT_LINKS if result.properties.get(p)]
        code_links = [p for p in _CODE_LINKS if result.properties.get(p)]
        if requirement_links:
            findings.append(
                Finding(
                    "error" if options.fail_on_skipped_verification else "warning",
                    target,
                    f"{key} is {result.result} but declares {', '.join(requirement_links)}",
                )
            )
        if code_links:
            findings.append(
                Finding("warning", target, f"{key} is {result.result} but declares {', '.join(code_links)}")
            )
    return findings


def check_testlogs(testlogs, options=None, expected_targets=None):
    """Check all reports below testlogs. Returns (report paths, findings)."""
    options = options or Options()
    testlogs = Path(testlogs)
    reports = sorted(testlogs.rglob("test.xml"))
    by_target = {}
    for xml_path in reports:
        by_target.setdefault(_target_of(testlogs, xml_path), []).append(xml_path)

    findings = []
    if expected_targets is not None:
        for target in sorted(set(expected_targets) - set(by_target)):
            findings.append(Finding("error", target, "expected test target has no test.xml (it did not run)"))
        for target in sorted(set(by_target) - set(expected_targets)):
            findings.append(Finding("warning", target, "report of a target that is not expected (stale?); not checked"))
            del by_target[target]
    if options.bazel_bin is None:
        findings.append(Finding("warning", "-", "--bazel-bin not given: reports not compared with the test lists"))

    for target, xml_paths in sorted(by_target.items()):
        findings.extend(check_target(target, xml_paths, options))
    return reports, findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--testlogs", required=True, help="Bazel test logs directory (bazel info bazel-testlogs)")
    parser.add_argument("--bazel-bin", help="Bazel output directory (bazel info bazel-bin); enables list comparison")
    parser.add_argument(
        "--expected-targets",
        help="file with the labels of all test targets that must have run (one per line)",
    )
    parser.add_argument(
        "--non-gtest",
        choices=("ignore", "warn", "error"),
        default="warn",
        help="how to treat reports not written by GoogleTest (default: warn)",
    )
    parser.add_argument(
        "--allow-missing-binary",
        action="store_true",
        help="a test binary missing below --bazel-bin is a warning instead of an error",
    )
    parser.add_argument(
        "--fail-on-skipped-verification",
        action="store_true",
        help="treat skipped/disabled tests with requirement links as errors",
    )
    parser.add_argument(
        "--fail-on-retried-tests",
        action="store_true",
        help="treat targets that needed more than one attempt as errors",
    )
    args = parser.parse_args(argv)

    if not Path(args.testlogs).is_dir():
        print(f"error: {args.testlogs} is not a directory", file=sys.stderr)
        return 1
    options = Options(
        bazel_bin=Path(args.bazel_bin) if args.bazel_bin else None,
        fail_on_skipped_verification=args.fail_on_skipped_verification,
        fail_on_retried_tests=args.fail_on_retried_tests,
        allow_missing_binary=args.allow_missing_binary,
        non_gtest=args.non_gtest,
    )
    expected = read_expected_targets(args.expected_targets) if args.expected_targets else None
    if expected is not None and not expected:
        print(f"error: {args.expected_targets} lists no test targets", file=sys.stderr)
        return 1
    reports, findings = check_testlogs(args.testlogs, options, expected)
    for finding in findings:
        where = "" if finding.target == "-" else f"//{finding.target}: "
        print(f"{finding.severity.upper()}: {where}{finding.message}")
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = len(findings) - errors
    print(f"checked {len(reports)} report(s): {errors} error(s), {warnings} warning(s)")
    if not reports:
        print("error: no test.xml found", file=sys.stderr)
        return 1
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
