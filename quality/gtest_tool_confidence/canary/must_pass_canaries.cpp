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

#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <memory>
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
    virtual int Get() = 0;
    virtual int Twice(int value) = 0;
    virtual void Read(int* out) = 0;
};

class MockInterface : public Interface
{
  public:
    MOCK_METHOD(void, Foo, (), (override));
    MOCK_METHOD(void, Bar, (int value), (override));
    MOCK_METHOD(int, Get, (), (override));
    MOCK_METHOD(int, Twice, (int value), (override));
    MOCK_METHOD(void, Read, (int* out), (override));
};

bool IsOdd(int value)
{
    return (value % 2) != 0;
}

bool IsGreater(int lhs, int rhs)
{
    return lhs > rhs;
}

struct Record
{
    int id;
};

// A float `ulps` units in the last place above 1.0F.
float OnePlusUlps(int ulps)
{
    float value = 1.0F;
    for (int i = 0; i < ulps; ++i)
    {
        value = std::nextafter(value, 2.0F);
    }
    return value;
}

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
    EXPECT_PRED1(IsOdd, One());
    EXPECT_PRED2(IsGreater, Two(), One());
    ASSERT_TRUE(One() < Two());
    ASSERT_THAT(One(), ::testing::Eq(1));
    ASSERT_EQ(Two(), 2);
}

TEST(CanaryMustPass, Matchers)
{
    const auto value = std::make_unique<int>(Two());
    EXPECT_THAT(std::string("canary"), ::testing::HasSubstr("nar"));
    EXPECT_THAT((std::vector<int>{Two(), One()}), ::testing::UnorderedElementsAre(1, 2));
    EXPECT_THAT((std::vector<int>{One(), Two()}), ::testing::Contains(2));
    EXPECT_THAT(One(), ::testing::AllOf(::testing::Gt(0), ::testing::Lt(2)));
    EXPECT_THAT(One(), ::testing::Not(::testing::Eq(2)));
    EXPECT_THAT(std::vector<int>{}, ::testing::IsEmpty());
    EXPECT_THAT(value.get(), ::testing::Pointee(2));
    EXPECT_THAT((Record{Two()}), ::testing::Field(&Record::id, 2));
}

// Counterparts of the boundary-input must-fail canaries: equal values of the
// same magnitude, length and representation shall pass.
TEST(CanaryMustPass, BoundaryInputs)
{
    EXPECT_EQ(std::numeric_limits<std::int64_t>::min() + One() - 1, std::numeric_limits<std::int64_t>::min());
    EXPECT_EQ(static_cast<std::uint64_t>(One()) << 63U, std::uint64_t{1U} << 63U);
    EXPECT_EQ(std::string(4096U, 'x') + "a", std::string(4096U, 'x') + "a");
    EXPECT_EQ(std::string("canary\0a", 8U), std::string("canary\0a", 8U));
    EXPECT_EQ(std::vector<int>(10000U, One()), std::vector<int>(10000U, 1));
    EXPECT_FLOAT_EQ(1.0F, OnePlusUlps(4));
    EXPECT_NEAR(1.0, 1.125, 0.125);
}

// The traceability properties used by S-CORE tests shall reach the XML report unchanged.
TEST(CanaryMustPass, RecordPropertyReachesReport)
{
    RecordProperty("PartiallyVerifies", "tool_req__gtest_canary_partially");
    RecordProperty("FullyVerifies", "tool_req__gtest_canary_fully");
    RecordProperty("Verifies", "::canary::Function()");
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

// gMock actions shall be performed as specified: a wrong return value or a
// missing side effect changes the behaviour of the code under test silently.
TEST(CanaryMustPassMock, ActionsPerformed)
{
    MockInterface mock;
    EXPECT_CALL(mock, Get()).WillOnce(::testing::Return(41)).WillRepeatedly(::testing::Return(7));
    EXPECT_CALL(mock, Twice(::testing::_)).WillRepeatedly(::testing::Invoke([](int value) {
        return 2 * value;
    }));
    EXPECT_CALL(mock, Read(::testing::NotNull())).WillOnce(::testing::SetArgPointee<0>(123));

    EXPECT_EQ(mock.Get(), 41);
    EXPECT_EQ(mock.Get(), 7);
    EXPECT_EQ(mock.Get(), 7);
    EXPECT_EQ(mock.Twice(Two() * 1000), 4000);
    int out = 0;
    mock.Read(&out);
    EXPECT_EQ(out, 123);
}

TEST(CanaryMustPassMock, OnCallDefaultAction)
{
    ::testing::NiceMock<MockInterface> mock;
    ON_CALL(mock, Get()).WillByDefault(::testing::Return(-5));
    ON_CALL(mock, Twice(Two())).WillByDefault(::testing::Return(99));
    EXPECT_EQ(mock.Get(), -5);
    EXPECT_EQ(mock.Twice(Two()), 99);
    // No ON_CALL matches: the built-in default value of the return type.
    EXPECT_EQ(mock.Twice(One()), 0);
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

// GTEST_SKIP() in SetUp() shall skip the test body and report the test as skipped.
class CanarySkipInSetUp : public ::testing::Test
{
  protected:
    void SetUp() override
    {
        GTEST_SKIP() << "canary skip in SetUp";
    }
};

TEST_F(CanarySkipInSetUp, SkippedIsNotPassed)
{
    FAIL() << "the test body ran although SetUp() skipped the test";
}

// A disabled test shall not be executed and shall not be reported as passed.
TEST(CanaryMustPass, DISABLED_DisabledIsNotPassed)
{
    FAIL() << "a disabled test was executed";
}
