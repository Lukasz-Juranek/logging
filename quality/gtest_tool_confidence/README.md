<!--
*******************************************************************************
Copyright (c) 2026 Contributors to the Eclipse Foundation

See the NOTICE file(s) distributed with this work for additional
information regarding copyright ownership.

This program and the accompanying materials are made available under the
terms of the Apache License Version 2.0 which is available at
https://www.apache.org/licenses/LICENSE-2.0

SPDX-License-Identifier: Apache-2.0
*******************************************************************************
-->

# GoogleTest tool confidence

Reference implementation of the detection measures that the GoogleTest Tool
Verification Report (`doc_tool__gtest` in
[eclipse-score/score](https://github.com/eclipse-score/score), folder
`docs/score_tools/tools_testing_frameworks/gtest`) requires as part of the
intended usage of GoogleTest/gMock.

With these measures in place, every safety-relevant potential malfunction of
GoogleTest is detected with sufficient confidence, so the report evaluates to
SCORE TCL HIGH (no qualification). Without them, GoogleTest is TCL LOW and would
have to be qualified by validation.

| Measure | What it detects | Where | When |
|---|---|---|---|
| M1 canary suite | GoogleTest/gMock does not report a deliberate failure, reports a false failure, reports skipped/disabled tests as passed, loses `RecordProperty()` values, exits with a wrong code, hides a premature `exit(0)` | `canary/` | every CI run, per toolchain configuration |
| M2 completeness check | Lost or missing test results, report/count inconsistencies, `<error>` test cases, skipped/disabled tests with requirement links | `completeness/` | after every unit-test run |
| M3 GoogleTest fault injection | The canary suite would miss a real GoogleTest/gMock defect (faults are injected into the GoogleTest sources) | `mutation/run_gtest_fault_injection.sh` | centrally, once per GoogleTest version / toolchain change |

Per module, only M1 and M2 are needed. M3 shows once, centrally, that M1 is
sensitive to real GoogleTest defects.

Mutation testing of a module's production code (`mutation/run_mutation.sh`)
measures the strength of that module's tests (ISO 26262-6 unit verification),
not the reliability of GoogleTest. It is an optional quality metric and not a
measure of the GoogleTest Tool Verification Report.

## M1: canary suite

* `must_fail_canaries.cpp` - one deliberate defect per assertion kind,
  exception assertion, fixture, parameterized/typed test, death test and gMock
  expectation in use. Each must be reported as failed.
* `must_pass_canaries.cpp` - passing counterparts, `RecordProperty()` values,
  a skipped and a disabled test, and gMock's default ("naggy") behaviour.
* `premature_exit_canary.cpp` - `exit(0)` inside a test must leave Bazel's
  `TEST_PREMATURE_EXIT_FILE` behind.
* `canary_expectations.json` - expected result of every canary and the
  `tool_req` it validates. Every test case must be listed; a new test case
  without expectation fails the check.
* `check_gtest_canaries.py` - the independent checker. GoogleTest does not
  judge itself: the checker reads exit codes, `--gtest_list_tests` and the XML
  report with plain Python, classifying results the same way docs-as-code does.

```sh
bazel test --config=x86_64-linux //quality/gtest_tool_confidence/...
```

The checker writes `gtest_canary_evidence.md` (one row per canary, grouped by
tool requirement) to the test's undeclared outputs
(`bazel-testlogs/quality/gtest_tool_confidence/canary/gtest_canary_test/test.outputs/`).

When a module starts to use a GoogleTest/gMock feature that has no canary, add
the canary and its expectation first.

## M2: test-run completeness check

```sh
bazel test --config=x86_64-linux //score/...
bazel run --config=x86_64-linux \
  //quality/gtest_tool_confidence/completeness:check_test_run_completeness -- \
  --testlogs "$(bazel info --config=x86_64-linux bazel-testlogs)" \
  --bazel-bin "$(bazel info --config=x86_64-linux bazel-bin)"
```

Add `--fail-on-skipped-verification` to turn skipped or disabled test cases that
declare `FullyVerifies`/`PartiallyVerifies` into errors.

## M3: GoogleTest fault injection with Mull

Requires `clang-19` and the matching Mull package
(`Mull-19-<version>-LLVM-19.1.1-ubuntu-amd64-24.04.deb` from
https://github.com/mull-project/mull/releases).

```sh
quality/gtest_tool_confidence/mutation/run_gtest_fault_injection.sh \
  --out gtest_fault_injection_report
```

The canary binaries are built with Clang; only the GoogleTest/gMock library
sources are instrumented (`gtest_fault_injection.yml`). Mull activates one fault
at a time and runs the canary checker (`--test-program`) against the faulty
GoogleTest. A fault is detected when any canary verdict, exit code, test list
or reported property changes. Every undetected fault in
`gtest_fault_injection_report/gtest_fault_injection.md` has to be classified:

* equivalent with respect to test verdicts and reports (e.g. console colouring,
  timing output, flag parsing not used by S-CORE), or
* a gap in the canary suite: add a canary that detects it.

CI: `.github/workflows/gtest_fault_injection.yml` (manual, and on changes of
`MODULE.bazel` or the canaries). The run uses a separate Bazel output base and
does not touch the workspace's `bazel-*` links.

## Optional: mutation testing of module code

`mutation/run_mutation.sh` mutates a module's production sources and runs its
real GoogleTest binary under Mull. It measures test strength, not GoogleTest:

```sh
quality/gtest_tool_confidence/mutation/run_mutation.sh \
  --target //score/mw/log/detail/wait_free_producer_queue:unit_test \
  --scope score/mw/log/detail/wait_free_producer_queue \
  --threshold 80 --out mutation_report
```

## Limitations

* The canary suite runs in the host configuration of this repository. QNX
  configurations need the same target in their test run.
* M3 runs on the Clang host build; GCC and QCC builds of GoogleTest are covered
  by M1 in each configuration.
* No assessor statement accepting canary tests or mutation testing as tool error
  detection is publicly available. Align the argument with the assessor early.
