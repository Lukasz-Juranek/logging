/********************************************************************************
 * Copyright (c) 2026 Contributors to the Eclipse Foundation
 *
 * See the NOTICE file(s) distributed with this work for additional
 * information regarding copyright ownership.
 *
 * This program and the accompanying materials are made available under the
 * terms of the Apache License Version 2.0 which is available at
 * https://www.apache.org/licenses/LICENSE-2.0
 *
 * SPDX-License-Identifier: Apache-2.0
 ********************************************************************************/

// GoogleTest canary for a premature exit.
//
// A test that calls exit(0) ends the process with exit code 0 before the
// remaining tests run and before the XML report is written. GoogleTest cannot
// report this itself; it creates the file named by TEST_PREMATURE_EXIT_FILE at
// start-up and removes it only on a normal end, and Bazel fails the test target
// if the file is left behind. The checker verifies that the file is left behind.

#include <gtest/gtest.h>

#include <cstdlib>

TEST(CanaryPrematureExit, ExitZeroInsideTest)
{
    std::exit(0);
}

TEST(CanaryPrematureExit, NeverReached)
{
    FAIL() << "a test after a premature exit was executed";
}
