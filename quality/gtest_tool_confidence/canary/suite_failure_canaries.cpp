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

// GoogleTest canaries for failures outside a test body.
//
// A failure in SetUpTestSuite() or TearDownTestSuite() belongs to the test suite,
// not to a test case: the test cases themselves may be reported as passed. Such
// a failure must still make the binary exit with a non-zero code and must appear
// in the XML report as an additional failed entry that --gtest_list_tests does
// not list. The checker pins this behaviour; the completeness check (M2) treats
// such entries as errors.

#include <gtest/gtest.h>

namespace
{

volatile int g_one = 1;

}  // namespace

class CanarySetUpTestSuiteFailure : public ::testing::Test
{
  protected:
    static void SetUpTestSuite()
    {
        ADD_FAILURE() << "canary failure in SetUpTestSuite";
    }
};

TEST_F(CanarySetUpTestSuiteFailure, BodyPasses)
{
    EXPECT_EQ(g_one, 1);
}

class CanaryTearDownTestSuiteFailure : public ::testing::Test
{
  protected:
    static void TearDownTestSuite()
    {
        ADD_FAILURE() << "canary failure in TearDownTestSuite";
    }
};

TEST_F(CanaryTearDownTestSuiteFailure, BodyPasses)
{
    EXPECT_EQ(g_one, 1);
}
