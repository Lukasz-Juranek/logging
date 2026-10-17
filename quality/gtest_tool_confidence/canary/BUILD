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

load("@rules_cc//cc:defs.bzl", "cc_binary")
load("@rules_python//python:defs.bzl", "py_library", "py_test")

# The canary binaries are deliberately not cc_test targets: most of them must
# fail. They are executed and judged by :gtest_canary_test. The key of each
# binary in canary_expectations.json is the target name without the
# "gtest_canary_" prefix.
_CANARIES = {
    "environment_failure": "environment_failure_canary.cpp",
    "must_fail": "must_fail_canaries.cpp",
    "must_pass": "must_pass_canaries.cpp",
    "premature_exit": "premature_exit_canary.cpp",
    "single_failure": "single_failure_canary.cpp",
    "suite_failure": "suite_failure_canaries.cpp",
}

[
    cc_binary(
        name = "gtest_canary_" + name,
        testonly = True,
        srcs = [src],
        deps = ["@googletest//:gtest_main"],
    )
    for name, src in _CANARIES.items()
]

py_library(
    name = "check_gtest_canaries_lib",
    srcs = ["check_gtest_canaries.py"],
    deps = ["//quality/gtest_tool_confidence/common:gtest_report"],
)

# Runs in every CI configuration that runs unit tests, so the canaries are
# compiled with the same toolchain, flags and GoogleTest version as the tests.
py_test(
    name = "gtest_canary_test",
    size = "small",
    srcs = ["check_gtest_canaries.py"],
    args = ["$(rootpath canary_expectations.json)"] + [
        "{}=$(rootpath :gtest_canary_{})".format(name, name)
        for name in _CANARIES
    ],
    data = ["canary_expectations.json"] + [":gtest_canary_" + name for name in _CANARIES],
    main = "check_gtest_canaries.py",
    deps = ["//quality/gtest_tool_confidence/common:gtest_report"],
)

# Runs the real docs-as-code result parser on the canary reports and requires
# the same classification as the checker (the checker re-implements it).
py_test(
    name = "docs_as_code_parity_test",
    size = "small",
    srcs = ["docs_as_code_parity_test.py"],
    args = ["$(rootpath :gtest_canary_{})".format(name) for name in _CANARIES],
    data = [":gtest_canary_" + name for name in _CANARIES],
    main = "docs_as_code_parity_test.py",
    deps = [
        "//quality/gtest_tool_confidence/common:gtest_report",
        "@score_docs_as_code//src/extensions/score_source_code_linker",
    ],
)

# Unit tests of the checker itself, with fake GoogleTest binaries: proves that
# the checker fails on wrong results (it must not pass a broken GoogleTest).
py_test(
    name = "check_gtest_canaries_test",
    size = "small",
    srcs = ["check_gtest_canaries_test.py"],
    data = ["canary_expectations.json"],
    main = "check_gtest_canaries_test.py",
    deps = [":check_gtest_canaries_lib"],
)
