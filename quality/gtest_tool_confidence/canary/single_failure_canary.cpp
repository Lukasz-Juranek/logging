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

// GoogleTest canary for the exit code with exactly one failure.
//
// The must-fail binary contains many failing tests, so it cannot detect an exit
// code that only reflects a failure when several tests failed, or only the
// first test. Here exactly one test, which is not the first, fails; the binary
// must exit with a non-zero code.

#include <gtest/gtest.h>

namespace
{

volatile int g_one = 1;

}  // namespace

TEST(CanarySingleFailure, Passes)
{
    EXPECT_EQ(g_one, 1);
}

TEST(CanarySingleFailure, OnlyThisFails)
{
    EXPECT_EQ(g_one, 2);
}

TEST(CanarySingleFailure, PassesAfterFailure)
{
    EXPECT_EQ(g_one, 1);
}
