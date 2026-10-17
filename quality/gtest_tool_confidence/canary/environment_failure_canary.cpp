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

// GoogleTest canary for a fatal failure in a global test environment.
//
// A fatal failure in ::testing::Environment::SetUp() prevents all tests from
// running. The binary must exit with a non-zero code, and the failure must
// appear in the XML report as an entry that --gtest_list_tests does not list.
// The test cases themselves are not executed; the checker pins how GoogleTest
// reports them (see canary_expectations.json), because docs-as-code would
// classify a test case without <failure>, <error> or <skipped> as passed.

#include <gtest/gtest.h>

namespace
{

class FailingEnvironment : public ::testing::Environment
{
  public:
    void SetUp() override
    {
        FAIL() << "canary fatal failure in Environment::SetUp";
    }
};

// Registered before main() runs; GoogleTest takes ownership.
::testing::Environment* const g_environment = ::testing::AddGlobalTestEnvironment(new FailingEnvironment);

}  // namespace

TEST(CanaryEnvironmentFailure, NotExecuted)
{
    FAIL() << "a test ran although the global environment set-up failed";
}
