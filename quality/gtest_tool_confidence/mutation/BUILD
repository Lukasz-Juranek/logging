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

load("@rules_python//python:defs.bzl", "py_binary", "py_test")

# The Mull runs need Clang and Mull and are started through
# run_gtest_fault_injection.sh and run_mutation.sh (see README.md); only the
# score evaluation is a Bazel target.
exports_files([
    "gtest_fault_injection.yml",
    "mull.yml",
    "run_gtest_fault_injection.sh",
    "run_mutation.sh",
])

py_binary(
    name = "mutation_score",
    srcs = ["mutation_score.py"],
)

py_binary(
    name = "fault_injection_driver",
    srcs = ["fault_injection_driver.py"],
)

py_test(
    name = "fault_injection_driver_test",
    size = "small",
    srcs = [
        "fault_injection_driver.py",
        "fault_injection_driver_test.py",
    ],
    main = "fault_injection_driver_test.py",
)

py_test(
    name = "mutation_score_test",
    size = "small",
    srcs = [
        "mutation_score.py",
        "mutation_score_test.py",
    ],
    main = "mutation_score_test.py",
)
