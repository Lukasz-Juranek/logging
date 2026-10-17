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

// GoogleTest canaries that MUST be reported as passed, skipped or disabled.
//
// Counterpart of must_fail_canaries.cpp: detects false failures (TVR malfunction
// "indicates presence of a non-existing error"), checks that skipped and disabled
// tests are not reported as passed, and checks that RecordProperty() values,
// which docs-as-code uses for requirement traceability, reach the XML report.

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace
{

volatile int g_one = 1;
volatile int g_two = 2;

int One()
{
    return g_one;
}

int Two()
{
    return g_two;
}

[[noreturn]] void DieWithMessage()
{
    std::cerr << "canary-death-message" << std::endl;
    std::abort();
}

void ThrowLogicError()
{
    throw std::logic_error("canary");
}

class Interface
{
  public:
    virtual ~Interface() = default;
    virtual void Foo() = 0;
    virtual void Bar(int value) = 0;
};

class MockInterface : public Interface
{
  public:
    MOCK_METHOD(void, Foo, (), (override));
    MOCK_METHOD(void, Bar, (int value), (override));
};

}  // namespace

TEST(CanaryMustPass, Assertions)
{
    EXPECT_EQ(One(), 1);
    EXPECT_NE(One(), Two());
    EXPECT_LT(One(), Two());
    EXPECT_LE(One(), One());
    EXPECT_GT(Two(), One());
    EXPECT_GE(Two(), Two());
    EXPECT_TRUE(One() < Two());
    EXPECT_FALSE(One() > Two());
    EXPECT_FLOAT_EQ(1.0F, 1.0F);
    EXPECT_DOUBLE_EQ(0.1 + 0.2, 0.3);
    EXPECT_NEAR(1.0, 1.05, 0.1);
    EXPECT_STREQ("canary", "canary");
    EXPECT_THAT((std::vector<int>{One(), Two()}), ::testing::ElementsAre(1, 2));
    EXPECT_THROW(ThrowLogicError(), std::logic_error);
    EXPECT_ANY_THROW(ThrowLogicError());
    EXPECT_NO_THROW(One());
    ASSERT_EQ(Two(), 2);
}

// The traceability properties used by S-CORE tests shall reach the XML report unchanged.
TEST(CanaryMustPass, RecordPropertyReachesReport)
{
    RecordProperty("PartiallyVerifies", "tool_req__gtest_canary_partially");
    RecordProperty("FullyVerifies", "tool_req__gtest_canary_fully");
    RecordProperty("Description", "GoogleTest canary for RecordProperty");
    RecordProperty("TestType", "requirements-based");
    RecordProperty("DerivationTechnique", "requirements-analysis");
    RecordProperty("ASIL", "B");
}

TEST(CanaryMustPassDeathTest, ExpectDeath)
{
    EXPECT_DEATH(DieWithMessage(), "canary-death-message");
}

TEST(CanaryMustPassDeathTest, ExpectExit)
{
    EXPECT_EXIT(std::exit(3), ::testing::ExitedWithCode(3), "");
}

TEST(CanaryMustPassMock, ExpectationsMet)
{
    ::testing::StrictMock<MockInterface> mock;
    ::testing::InSequence sequence;
    EXPECT_CALL(mock, Foo()).Times(1);
    EXPECT_CALL(mock, Bar(5)).Times(2);
    mock.Foo();
    mock.Bar(5);
    mock.Bar(5);
}

TEST(CanaryMustPassMock, NiceMockUninterestingCall)
{
    ::testing::NiceMock<MockInterface> mock;
    mock.Foo();
}

// Documents gMock's default ("naggy") behaviour: an uninteresting call only
// prints a warning and does NOT fail the test. Tests that must detect
// unexpected calls have to use StrictMock or EXPECT_CALL(...).Times(0).
// If this canary ever fails, the behaviour changed and the GoogleTest TVR's
// constraints of use must be reviewed.
TEST(CanaryMustPassMock, NaggyMockUninterestingCallOnlyWarns)
{
    MockInterface mock;
    mock.Foo();
}

// A skipped test shall be reported as skipped, never as passed.
TEST(CanaryMustPass, SkippedIsNotPassed)
{
    RecordProperty("PartiallyVerifies", "tool_req__gtest_canary_skipped");
    GTEST_SKIP() << "canary skip";
}

// A disabled test shall not be executed and shall not be reported as passed.
TEST(CanaryMustPass, DISABLED_DisabledIsNotPassed)
{
    FAIL() << "a disabled test was executed";
}
