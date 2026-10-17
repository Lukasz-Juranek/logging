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

// GoogleTest canaries that MUST be reported as failed.
//
// Each test contains a deliberate defect that a correctly working GoogleTest/gmock
// shall detect. The binary is not a Bazel test: it is executed by the independent
// checker (check_gtest_canaries.py), which compares the reported result of every
// test case against canary_expectations.json. A canary reported as "passed" is a
// detected false-pass malfunction of the test framework (TVR malfunction
// "fails to detect an existing error").

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace
{

// Opaque values: prevent the compiler from folding the comparisons below.
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

void DoNothing() {}

void ThrowLogicError()
{
    throw std::logic_error("canary");
}

[[noreturn]] void DieWithMessage()
{
    std::cerr << "canary-death-message" << std::endl;
    std::abort();
}

struct AlwaysUnequal
{
    int value;
};

bool operator==(const AlwaysUnequal&, const AlwaysUnequal&)
{
    return false;
}

std::ostream& operator<<(std::ostream& os, const AlwaysUnequal& v)
{
    return os << "AlwaysUnequal{" << v.value << "}";
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

void AssertInHelper()
{
    ASSERT_EQ(One(), Two());
}

}  // namespace

// ---------------------------------------------------------------- assertions

TEST(CanaryMustFail, ExpectEq)
{
    EXPECT_EQ(One(), Two());
}

TEST(CanaryMustFail, ExpectEqCustomOperator)
{
    EXPECT_EQ(AlwaysUnequal{1}, AlwaysUnequal{1});
}

TEST(CanaryMustFail, ExpectNe)
{
    EXPECT_NE(One(), One());
}

TEST(CanaryMustFail, ExpectLt)
{
    EXPECT_LT(Two(), One());
}

TEST(CanaryMustFail, ExpectLe)
{
    EXPECT_LE(Two(), One());
}

TEST(CanaryMustFail, ExpectGt)
{
    EXPECT_GT(One(), Two());
}

TEST(CanaryMustFail, ExpectGe)
{
    EXPECT_GE(One(), Two());
}

TEST(CanaryMustFail, ExpectTrue)
{
    EXPECT_TRUE(One() == Two());
}

TEST(CanaryMustFail, ExpectFalse)
{
    EXPECT_FALSE(One() == One());
}

TEST(CanaryMustFail, ExpectFloatEq)
{
    EXPECT_FLOAT_EQ(1.0F, 1.1F);
}

TEST(CanaryMustFail, ExpectDoubleEq)
{
    EXPECT_DOUBLE_EQ(1.0, 1.0000001);
}

TEST(CanaryMustFail, ExpectNear)
{
    EXPECT_NEAR(1.0, 1.2, 0.1);
}

TEST(CanaryMustFail, ExpectStrEq)
{
    EXPECT_STREQ("canary", "canarz");
}

TEST(CanaryMustFail, ExpectThatMatcher)
{
    const std::vector<int> values{One(), Two() + One()};
    EXPECT_THAT(values, ::testing::ElementsAre(1, 2));
}

TEST(CanaryMustFail, ExpectThrowButNothingThrown)
{
    EXPECT_THROW(DoNothing(), std::logic_error);
}

TEST(CanaryMustFail, ExpectThrowWrongType)
{
    EXPECT_THROW(ThrowLogicError(), std::runtime_error);
}

TEST(CanaryMustFail, ExpectNoThrowButThrown)
{
    EXPECT_NO_THROW(ThrowLogicError());
}

TEST(CanaryMustFail, ExpectAnyThrowButNothingThrown)
{
    EXPECT_ANY_THROW(DoNothing());
}

TEST(CanaryMustFail, AddFailure)
{
    ADD_FAILURE() << "canary";
}

TEST(CanaryMustFail, Fail)
{
    FAIL() << "canary";
}

TEST(CanaryMustFail, UncaughtException)
{
    ThrowLogicError();
}

// A fatal assertion shall stop the test: the property below must not be recorded.
TEST(CanaryMustFail, AssertEqStopsTest)
{
    ASSERT_EQ(One(), Two());
    RecordProperty("ReachedAfterFatalAssertion", "yes");
}

// A fatal assertion in a helper function shall still fail the calling test.
TEST(CanaryMustFail, AssertInHelperFunction)
{
    AssertInHelper();
}

// ----------------------------------------------------------- test structure

class CanaryFixture : public ::testing::Test
{
  protected:
    void SetUp() override
    {
        ADD_FAILURE() << "canary failure in SetUp";
    }
};

TEST_F(CanaryFixture, FailureInSetUp) {}

class CanaryParam : public ::testing::TestWithParam<int>
{
};

// Only the instance with parameter 2 shall fail; 1 and 3 shall pass.
TEST_P(CanaryParam, OnlyTwoFails)
{
    EXPECT_NE(GetParam(), Two());
}

INSTANTIATE_TEST_SUITE_P(Values, CanaryParam, ::testing::Values(1, 2, 3));

template <typename T>
class CanaryTyped : public ::testing::Test
{
};

using CanaryTypes = ::testing::Types<int, double>;
TYPED_TEST_SUITE(CanaryTyped, CanaryTypes);

// Shall pass for int and fail for double.
TYPED_TEST(CanaryTyped, OnlyIntPasses)
{
    EXPECT_EQ(sizeof(TypeParam), sizeof(int));
}

// --------------------------------------------------------------- death tests

TEST(CanaryMustFailDeathTest, ExpectDeathButSurvives)
{
    EXPECT_DEATH(DoNothing(), "");
}

TEST(CanaryMustFailDeathTest, ExpectDeathWrongMessage)
{
    EXPECT_DEATH(DieWithMessage(), "message-that-is-never-printed");
}

TEST(CanaryMustFailDeathTest, ExpectExitWrongCode)
{
    EXPECT_EXIT(std::exit(1), ::testing::ExitedWithCode(0), "");
}

// ---------------------------------------------------------------------- gmock

TEST(CanaryMustFailMock, UnmetExpectation)
{
    MockInterface mock;
    EXPECT_CALL(mock, Foo()).Times(1);
}

TEST(CanaryMustFailMock, CalledTooOften)
{
    MockInterface mock;
    EXPECT_CALL(mock, Foo()).Times(1);
    mock.Foo();
    mock.Foo();
}

TEST(CanaryMustFailMock, WrongArgument)
{
    MockInterface mock;
    EXPECT_CALL(mock, Bar(5)).Times(::testing::AnyNumber());
    mock.Bar(6);
}

TEST(CanaryMustFailMock, StrictMockUninterestingCall)
{
    ::testing::StrictMock<MockInterface> mock;
    mock.Foo();
}

TEST(CanaryMustFailMock, SequenceViolated)
{
    MockInterface mock;
    ::testing::InSequence sequence;
    EXPECT_CALL(mock, Foo());
    EXPECT_CALL(mock, Bar(1));
    mock.Bar(1);
    mock.Foo();
}
