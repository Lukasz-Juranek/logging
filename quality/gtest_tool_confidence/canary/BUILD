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
load("@rules_python//python:defs.bzl", "py_test")

# The canary binaries are deliberately not cc_test targets: the failing one
# must fail. They are executed and judged by :gtest_canary_test.
cc_binary(
    name = "gtest_canary_must_fail",
    testonly = True,
    srcs = ["must_fail_canaries.cpp"],
    deps = ["@googletest//:gtest_main"],
)

cc_binary(
    name = "gtest_canary_must_pass",
    testonly = True,
    srcs = ["must_pass_canaries.cpp"],
    deps = ["@googletest//:gtest_main"],
)

cc_binary(
    name = "gtest_canary_premature_exit",
    testonly = True,
    srcs = ["premature_exit_canary.cpp"],
    deps = ["@googletest//:gtest_main"],
)

# Runs in every CI configuration that runs unit tests, so the canaries are
# compiled with the same toolchain, flags and GoogleTest version as the tests.
py_test(
    name = "gtest_canary_test",
    size = "small",
    srcs = ["check_gtest_canaries.py"],
    args = [
        "$(rootpath canary_expectations.json)",
        "$(rootpath :gtest_canary_must_fail)",
        "$(rootpath :gtest_canary_must_pass)",
        "$(rootpath :gtest_canary_premature_exit)",
    ],
    data = [
        "canary_expectations.json",
        ":gtest_canary_must_fail",
        ":gtest_canary_must_pass",
        ":gtest_canary_premature_exit",
    ],
    main = "check_gtest_canaries.py",
    deps = ["//quality/gtest_tool_confidence/common:gtest_report"],
)
