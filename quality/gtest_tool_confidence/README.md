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

Reference implementation of the measures that the GoogleTest Tool Verification
Report (`doc_tool__gtest` in
[eclipse-score/score](https://github.com/eclipse-score/score), folder
`docs/score_tools/tools_testing_frameworks/gtest`) names for the intended usage
of GoogleTest/gMock.

The report evaluates GoogleTest to **SCORE TCL LOW**: the measures below do not
yet show with sufficient confidence that a GoogleTest malfunction in a real
test is detected (see "Limitations"). GoogleTest is therefore to be qualified
by validation (ISO 26262-8, 11.4.9), with the canary suite (M1) as the
validation suite in the target tool configuration. M2 and M4 remain detection
measures in every test run; M3 measures the sensitivity of the validation
suite.

| Measure | What it does | Where | When |
|---|---|---|---|
| M1 canary suite | Validates GoogleTest/gMock in the tool configuration of the tests: deliberate failures must be reported as failed, correct tests as passed, skipped/disabled tests as such, `RecordProperty()` values must reach the right test case, the exit code and the premature-exit marker must be correct | `canary/` | every CI run, per toolchain configuration |
| M2 completeness check | Detects in every real test run: test targets without report, lost or unlisted results, filtered runs, count mismatches, failed or `<error>` test cases after a green run, failures outside a test case, retried targets, skipped/disabled tests with requirement links | `completeness/` | after every unit-test run |
| M3 GoogleTest fault injection | Measures how many faults injected into the compiled GoogleTest/gMock sources the canary checker detects | `mutation/run_gtest_fault_injection.sh` | centrally, once per GoogleTest version / toolchain change |

Mutation testing of a module's production code (`mutation/run_mutation.sh`)
measures the strength of that module's tests (ISO 26262-6 unit verification),
not the reliability of GoogleTest. It is an optional quality metric and not a
measure of the GoogleTest Tool Verification Report.

## M1: canary suite

| Binary | Content | Expected |
|---|---|---|
| `must_fail_canaries.cpp` | one deliberate defect per assertion kind (`EXPECT_*`, `ASSERT_*`, `EXPECT_PRED*`, matchers, exception assertions), boundary inputs (64-bit extremes, long strings, embedded NUL, long containers, 5 ULP floats, NaN), a failure in another thread, `SetUp()`/`TearDown()` failures, parameterized/typed tests, death tests and gMock expectations | failed (parameterized/typed: only the defective instance) |
| `must_pass_canaries.cpp` | passing counterparts, matchers, boundary inputs, gMock actions (`Return`, `WillOnce`/`WillRepeatedly`, `Invoke`, `SetArgPointee`, `ON_CALL`), `RecordProperty()` values, `GTEST_SKIP()` in a test and in `SetUp()`, a disabled test, gMock's default ("naggy") behaviour | passed / skipped / disabled |
| `single_failure_canary.cpp` | exactly one failing test, not the first | non-zero exit code |
| `suite_failure_canaries.cpp` | failures in `SetUpTestSuite()` and `TearDownTestSuite()` | non-zero exit code, failed suite-level report entry |
| `environment_failure_canary.cpp` | fatal failure in a global `Environment::SetUp()` | non-zero exit code, test reported as skipped, failed report entry |
| `premature_exit_canary.cpp` | `exit(0)` inside a test | exit code 0, `TEST_PREMATURE_EXIT_FILE` left behind, report missing or incomplete |

* `canary_expectations.json` - expected result of every canary and the
  `tool_req` it validates. Every listed test case must have an expectation and
  vice versa; report entries that the binary does not list must be expected
  explicitly.
* `check_gtest_canaries.py` - the independent checker. GoogleTest does not
  judge itself: the checker reads exit codes, the premature-exit marker,
  `--gtest_list_tests` and the XML report with plain Python. A test case may
  only report the properties it recorded, so a property attached to the wrong
  test case is detected.
* `check_gtest_canaries_test.py` - unit tests of the checker with fake
  GoogleTest binaries. Each simulates one malfunction (false pass, false
  failure, wrong exit code, lost or extra result, lost or misplaced property,
  premature exit hidden, ...) and requires the checker to fail.
* `docs_as_code_parity_test.py` - runs the real docs-as-code result parser on
  all canary reports and on edge cases and requires the same classification as
  the checker.

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
bazel query 'tests(//score/...)' > expected_tests.txt   # same scope and filters as the test run
bazel run --config=x86_64-linux \
  //quality/gtest_tool_confidence/completeness:check_test_run_completeness -- \
  --testlogs "$(bazel info --config=x86_64-linux bazel-testlogs)" \
  --bazel-bin "$(bazel info --config=x86_64-linux bazel-bin)" \
  --expected-targets expected_tests.txt \
  --fail-on-skipped-verification
```

CI (`.github/workflows/build.yml`) runs it with `--expected-targets` and
`--fail-on-skipped-verification`. Further options: `--non-gtest
{ignore,warn,error}` for reports not written by GoogleTest (default: warning),
`--allow-missing-binary`, `--fail-on-retried-tests`. Sharded targets are merged
before the comparison with the test list.

## M3: GoogleTest fault injection with Mull

Requires `clang-19` and the matching Mull package
(`Mull-19-0.34.2-LLVM-19.1.1-ubuntu-amd64-24.04.deb` from
https://github.com/mull-project/mull/releases; the workflow verifies its
SHA-256).

```sh
quality/gtest_tool_confidence/mutation/run_gtest_fault_injection.sh \
  --out gtest_fault_injection_report
```

The canary binaries are built with Clang at `-O0`; only the GoogleTest/gMock
library sources (`googletest/src`, `googlemock/src`) are instrumented
(`gtest_fault_injection.yml`). Mull is used only to discover the mutants
(`--dry-run`). `fault_injection_driver.py` then activates one mutant at a time
and runs the canary checker directly; mull-runner's verdicts for an external
`--test-program` were found unreliable (a mutant reported as killed that the
checker does not detect when run directly). A mutant is detected when any
canary verdict, exit code, test list or reported property changes.

Every undetected mutant in
`gtest_fault_injection_report/gtest_fault_injection.md` has to be classified:

* **equivalent**: the mutated code cannot change a verdict, exit code, test
  list or XML report in the intended usage (e.g. console colouring, timing
  output, flags not used by S-CORE). The justification names the code path;
  a second person confirms it;
* **gap**: add a canary that detects it and re-run the campaign.

Acceptance: no unclassified mutant and no open gap. The detection rate itself
is reported, not gated (`--threshold 0`).

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

Its surviving mutants are not classified yet.

## Limitations

* **Canaries are not the real tests.** The canaries cover the features in the
  inventory above with chosen inputs. An input-dependent GoogleTest defect that
  only shows with the values of a real test is not detected by M1. This is why
  the report evaluates to TCL LOW and relies on qualification by validation.
* **M3 scope.** Header-only GoogleTest/gMock code (assertion helpers such as
  `CmpHelperEQ`, most matchers, `gmock-spec-builders.h`, the
  parameterized/typed test machinery) is instantiated in the canary sources and
  is not mutated. M3 runs with Clang at `-O0`; the production GCC and QCC
  builds of GoogleTest are not fault-injected.
* **M3 result pending.** The campaign with GoogleTest 1.17.0.bcr.2 found 1,710
  mutants; their execution and classification are not archived yet.
* **x86_64-linux only.** M1 and M2 run in the x86_64-linux CI configuration
  (GCC 12). QNX (QCC, `arm64-qnx`, `x86_64-qnx`) is not covered: death tests
  and process handling differ there.
* **Common cause of M2's list comparison.** `--gtest_list_tests` and the XML
  report are produced by the same GoogleTest binary from the same test
  registry; a test that is never registered is missing from both.
* **docs-as-code and suite-level failures.** GoogleTest reports a failure in
  `SetUpTestSuite()`, `TearDownTestSuite()` or a global `Environment` as a
  `<testcase>` without `name` and `classname`; docs-as-code's XML reader
  asserts that one of them is set.

## Open items

* Run the canary suite and M2 in the QNX configurations (QEMU test runner).
* Archive the M3 campaign result with every undetected mutant classified.
* Move M1-M3 to a central package (e.g. `score_tooling`) used by all modules,
  and enforce in CI that every module using GoogleTest runs M1 and M2 and uses
  the evaluated GoogleTest version (M5).
* Link the canaries to the `tool_req` needs with `FullyVerifies`, so that
  docs-as-code produces the qualification evidence.
* Classify the surviving mutants of the optional production-code mutation run.
* Assessor review of the argument (confirmation review).
