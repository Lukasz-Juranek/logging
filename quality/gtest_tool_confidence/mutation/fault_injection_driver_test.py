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
"""Unit tests for fault_injection_driver.py with a fake checker and fake mutants."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from quality.gtest_tool_confidence.mutation import fault_injection_driver as driver

# Fake checker: fails for "kill" mutants, hangs for "hang" mutants, passes
# otherwise. Exits with 3 if more than one mutant is active at a time or if it
# does not run in a fresh, empty working directory.
_FAKE_CHECKER = """
import os
import sys
import time

active = [name for name, value in os.environ.items() if name.startswith("fake_mutant_") and value == "1"]
if len(active) > 1 or os.listdir("."):
    sys.exit(3)
open("scratch", "w").close()
if active and "_kill_" in active[0]:
    sys.exit(1)
if active and "_hang_" in active[0]:
    time.sleep(30)
sys.exit(0)
"""


def _mutant(mutant_id, line):
    return {"id": mutant_id, "mutatorName": "cxx_eq_to_ne", "location": {"start": {"line": line, "column": 1}}}


_MUTANTS = {
    "schemaVersion": "1",
    "files": {
        "external/googletest+/googletest/src/gtest.cc": {
            "mutants": [
                _mutant("fake_mutant_kill_1", 10),
                _mutant("fake_mutant_survive_1", 20),
                _mutant("fake_mutant_hang_1", 30),
            ]
        },
        "external/googletest+/googlemock/src/gmock-spec-builders.cc": {
            "mutants": [_mutant("fake_mutant_kill_2", 40), _mutant("fake_mutant_survive_2", 50)]
        },
    },
}


class FaultInjectionDriverTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.checker = self.dir / "fake_checker.py"
        self.checker.write_text(_FAKE_CHECKER, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, mutants, checker_args=(), timeout="2"):
        mutants_path = self.dir / "mutants.json"
        mutants_path.write_text(json.dumps(mutants), encoding="utf-8")
        output = self.dir / "result.json"
        argv = [
            "--mutants",
            str(mutants_path),
            "--output",
            str(output),
            "--workers",
            "2",
            "--timeout",
            timeout,
            "--",
            sys.executable,
            str(self.checker),
            *checker_args,
        ]
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = driver.main(argv)
        result = json.loads(output.read_text(encoding="utf-8")) if output.exists() else None
        return code, result, stderr.getvalue()

    @staticmethod
    def _statuses(result):
        return {m["id"]: m["status"] for f in result["files"].values() for m in f["mutants"]}

    def test_each_mutant_gets_its_verdict(self):
        code, result, _ = self._run(_MUTANTS)
        self.assertEqual(code, 0)
        self.assertEqual(
            self._statuses(result),
            {
                "fake_mutant_kill_1": "Killed",
                "fake_mutant_survive_1": "Survived",
                "fake_mutant_hang_1": "Timeout",
                "fake_mutant_kill_2": "Killed",
                "fake_mutant_survive_2": "Survived",
            },
        )

    def test_result_keeps_the_mutant_locations(self):
        _, result, _ = self._run(_MUTANTS)
        mutant = result["files"]["external/googletest+/googletest/src/gtest.cc"]["mutants"][1]
        self.assertEqual(mutant["location"]["start"]["line"], 20)

    def test_failing_baseline_aborts(self):
        broken = self.dir / "broken_checker.py"
        broken.write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
        self.checker = broken
        code, result, stderr = self._run(_MUTANTS)
        self.assertEqual(code, 2)
        self.assertIsNone(result)
        self.assertIn("baseline: Killed", stderr)

    def test_report_without_mutants_is_an_error(self):
        code, result, stderr = self._run({"files": {}})
        self.assertEqual(code, 2)
        self.assertIsNone(result)
        self.assertIn("no mutants", stderr)

    def test_missing_checker_command_is_an_error(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            driver.main(["--mutants", "m.json", "--output", "o.json"])


if __name__ == "__main__":
    unittest.main()
