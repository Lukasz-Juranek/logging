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
"""Independent reading of GoogleTest XML reports and test lists.

Used by the GoogleTest canary checker and the test-run completeness check. Kept
deliberately small and free of third-party dependencies so that it can be
reviewed completely.

The result classification mirrors ``parse_testcase_result`` in docs-as-code
(``src/extensions/score_source_code_linker/xml_parser.py``), because that is
how S-CORE turns the XML report into requirement-verification evidence:

* ``status="notrun"``                          -> ``disabled``
* no ``<failure>``, ``<error>``, ``<skipped>``    -> ``passed``
* ``<failure>`` or ``<error>``                   -> ``failed``
* ``<skipped>``                                -> ``skipped``

GoogleTest reports a failure outside a test case (``SetUpTestSuite()``,
``TearDownTestSuite()``, a global ``Environment``) as an additional
``<testcase>`` with empty ``name`` and ``classname``. --gtest_list_tests does
not list it. It is keyed here as ``<testsuite name>.(suite-level)``.
"""

import dataclasses
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

# Attributes GoogleTest itself writes on <testcase>. Anything else is a
# RecordProperty() value (older GoogleTest versions write them as attributes).
_GTEST_TESTCASE_ATTRIBUTES = frozenset(
    {
        "name",
        "classname",
        "status",
        "result",
        "time",
        "timestamp",
        "file",
        "line",
        "value_param",
        "type_param",
    }
)

# Environment variables through which Bazel or a surrounding test run would
# redirect, filter or shard a GoogleTest binary started by these tools.
_INHERITED_TEST_ENV = (
    "XML_OUTPUT_FILE",
    "GTEST_OUTPUT",
    "GTEST_FILTER",
    "GTEST_ALSO_RUN_DISABLED_TESTS",
    "GTEST_FAIL_FAST",
    "GTEST_BRIEF",
    "GTEST_SHARD_INDEX",
    "GTEST_TOTAL_SHARDS",
    "GTEST_SHARD_STATUS_FILE",
    "TEST_SHARD_INDEX",
    "TEST_TOTAL_SHARDS",
    "TEST_SHARD_STATUS_FILE",
    "TEST_PREMATURE_EXIT_FILE",
    "TEST_WARNINGS_OUTPUT_FILE",
    "TESTBRIDGE_TEST_ONLY",
    "TESTBRIDGE_TEST_RUNNER_FAIL_FAST",
)


# Key suffix for a failure outside a test case (see module docstring).
SUITE_LEVEL = "(suite-level)"


@dataclasses.dataclass(frozen=True)
class TestcaseResult:
    key: str
    result: str
    message: str
    properties: dict


def clean_test_env(extra=None):
    """Return a copy of the environment without test-runner redirections."""
    env = {k: v for k, v in os.environ.items() if k not in _INHERITED_TEST_ENV}
    if extra:
        env.update(extra)
    return env


def testcase_key(testcase, suite_name=""):
    classname = testcase.get("classname", "")
    name = testcase.get("name", "")
    if not classname and not name:
        return f"{suite_name}.{SUITE_LEVEL}"
    return f"{classname}.{name}"


def is_suite_level(key):
    return key.endswith(f".{SUITE_LEVEL}")


def iter_testcases(root):
    """Yield (key, <testcase> element) for every test case of a report."""
    # root.iter() includes the root itself if it is a <testsuite>.
    suites = list(root.iter("testsuite"))
    if root.tag != "testsuite":
        suites.insert(0, root)
    for suite in suites:
        for testcase in suite.findall("testcase"):
            yield testcase_key(testcase, suite.get("name", "")), testcase


def classify(testcase):
    """Return (result, message) for a <testcase> element."""
    if testcase.get("status") == "notrun":
        return "disabled", ""
    failure = testcase.find("failure")
    error = testcase.find("error")
    skipped = testcase.find("skipped")
    if failure is None and error is None and skipped is None:
        return "passed", ""
    if failure is not None:
        return "failed", failure.get("message", "")
    if error is not None:
        return "failed", error.get("message", "")
    return "skipped", skipped.get("message", "")


def properties_of(testcase):
    props = {
        name: value
        for name, value in testcase.attrib.items()
        if name not in _GTEST_TESTCASE_ATTRIBUTES
    }
    for prop in testcase.findall("./properties/property"):
        props[prop.get("name", "")] = prop.get("value", "")
    return props


def parse_report(xml_path):
    """Parse a GoogleTest XML report into {key: TestcaseResult}.

    Raises ValueError on duplicate test case keys, which would make a lost
    result indistinguishable from a reported one.
    """
    root = ET.parse(xml_path).getroot()
    results = {}
    for key, testcase in iter_testcases(root):
        if key in results:
            raise ValueError(f"{xml_path}: duplicate test case {key}")
        result, message = classify(testcase)
        results[key] = TestcaseResult(key, result, message, properties_of(testcase))
    return results


def declared_test_count(xml_path):
    """Return the 'tests' count declared by the report's root element, or None."""
    root = ET.parse(xml_path).getroot()
    value = root.get("tests")
    return int(value) if value is not None else None


def is_gtest_report(xml_path):
    """True if the report was written by GoogleTest (not Bazel's fallback XML).

    GoogleTest names its root element "AllTests" and writes a classname on
    every test case; Bazel's generated fallback report does neither.
    """
    root = ET.parse(xml_path).getroot()
    if root.get("name") == "AllTests":
        return True
    testcases = list(root.iter("testcase"))
    return bool(testcases) and all("classname" in tc.attrib for tc in testcases)


def parse_test_list(output):
    """Parse the output of ``--gtest_list_tests`` into a list of keys.

    The banner printed by gtest_main/gmock_main ("Running main() from ...")
    is skipped; any other unexpected line is an error.
    """
    keys = []
    suite = None
    for raw_line in output.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if suite is None and raw_line.startswith("Running main() from "):
            continue
        if not raw_line.startswith(" "):
            suite = line.strip()
            if not suite.endswith("."):
                raise ValueError(f"unexpected test list line: {raw_line!r}")
            suite = suite[:-1]
        else:
            if suite is None:
                raise ValueError(f"test name without suite: {raw_line!r}")
            keys.append(f"{suite}.{line.strip()}")
    return keys


def list_tests(binary, cwd=None, env=None):
    """Run ``binary --gtest_list_tests`` and return the listed keys."""
    completed = subprocess.run(
        [str(binary), "--gtest_list_tests"],
        cwd=cwd,
        env=env if env is not None else clean_test_env(),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"{binary} --gtest_list_tests exited with {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    return parse_test_list(completed.stdout)


def run_with_report(binary, xml_path, cwd=None, timeout=600, extra_env=None):
    """Run a GoogleTest binary, writing its XML report to xml_path.

    Returns the process exit code.
    """
    xml_path = Path(xml_path)
    if xml_path.exists():
        xml_path.unlink()
    completed = subprocess.run(
        [str(binary), f"--gtest_output=xml:{xml_path}"],
        cwd=cwd,
        env=clean_test_env(extra_env),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return completed.returncode
