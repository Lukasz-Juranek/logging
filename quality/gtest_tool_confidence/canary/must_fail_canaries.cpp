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

#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
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

bool IsEven(int value)
{
    return (value % 2) == 0;
}

bool IsGreater(int lhs, int rhs)
{
    return lhs > rhs;
}

struct Record
{
    int id;
};

// Returns `count` copies of `fill`, with the last element replaced by `last`.
std::vector<int> LongVector(std::size_t count, int fill, int last)
{
    std::vector<int> values(count, fill);
    values.back() = last;
    return values;
}

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

TEST(CanaryMustFail, AssertTrueStopsTest)
{
    ASSERT_TRUE(One() == Two());
    RecordProperty("ReachedAfterFatalAssertion", "yes");
}

TEST(CanaryMustFail, AssertThatStopsTest)
{
    ASSERT_THAT(One(), ::testing::Eq(Two()));
    RecordProperty("ReachedAfterFatalAssertion", "yes");
}

TEST(CanaryMustFail, ExpectPred1)
{
    EXPECT_PRED1(IsEven, One());
}

TEST(CanaryMustFail, ExpectPred2)
{
    EXPECT_PRED2(IsGreater, One(), Two());
}

// A failure raised in another thread shall fail the test that started the thread.
TEST(CanaryMustFail, ExpectInOtherThread)
{
    std::thread worker([]() {
        EXPECT_EQ(One(), Two());
    });
    worker.join();
}

// ---------------------------------------------------------------- matchers

TEST(CanaryMustFail, MatcherHasSubstr)
{
    EXPECT_THAT(std::string("canary"), ::testing::HasSubstr("canarz"));
}

TEST(CanaryMustFail, MatcherUnorderedElementsAre)
{
    EXPECT_THAT((std::vector<int>{One(), Two()}), ::testing::UnorderedElementsAre(2, 2));
}

TEST(CanaryMustFail, MatcherContains)
{
    EXPECT_THAT((std::vector<int>{One(), One()}), ::testing::Contains(Two()));
}

TEST(CanaryMustFail, MatcherAllOf)
{
    EXPECT_THAT(One(), ::testing::AllOf(::testing::Gt(0), ::testing::Lt(1)));
}

TEST(CanaryMustFail, MatcherNot)
{
    EXPECT_THAT(One(), ::testing::Not(::testing::Eq(1)));
}

TEST(CanaryMustFail, MatcherIsEmpty)
{
    EXPECT_THAT((std::vector<int>{One()}), ::testing::IsEmpty());
}

TEST(CanaryMustFail, MatcherPointee)
{
    const auto value = std::make_unique<int>(One());
    EXPECT_THAT(value.get(), ::testing::Pointee(Two()));
}

TEST(CanaryMustFail, MatcherField)
{
    EXPECT_THAT((Record{One()}), ::testing::Field(&Record::id, Two()));
}

// ------------------------------------------- non-trivial and boundary inputs
//
// The canaries above use small integers. These ones check that the verdict
// does not depend on the magnitude, length or representation of the values.

TEST(CanaryMustFail, ExpectEqInt64Extremes)
{
    EXPECT_EQ(std::numeric_limits<std::int64_t>::min() + One() - 1, std::numeric_limits<std::int64_t>::max());
}

TEST(CanaryMustFail, ExpectEqUint64DiffersInTopBit)
{
    const std::uint64_t value = static_cast<std::uint64_t>(One()) << 63U;
    EXPECT_EQ(value, std::uint64_t{0U});
}

TEST(CanaryMustFail, ExpectEqLongStringDiffersAtEnd)
{
    const std::string lhs = std::string(4096U, 'x') + "a";
    const std::string rhs = std::string(4096U, 'x') + "b";
    EXPECT_EQ(lhs, rhs);
}

TEST(CanaryMustFail, ExpectEqStringWithEmbeddedNul)
{
    const std::string lhs("canary\0a", 8U);
    const std::string rhs("canary\0b", 8U);
    EXPECT_EQ(lhs, rhs);
}

TEST(CanaryMustFail, ExpectEqLongVectorDiffersAtEnd)
{
    EXPECT_EQ(LongVector(10000U, One(), One()), LongVector(10000U, One(), Two()));
}

// EXPECT_FLOAT_EQ accepts 4 ULPs; 5 ULPs shall fail.
TEST(CanaryMustFail, ExpectFloatEqFiveUlps)
{
    EXPECT_FLOAT_EQ(1.0F, OnePlusUlps(5));
}

TEST(CanaryMustFail, ExpectFloatEqNan)
{
    const float nan = std::numeric_limits<float>::quiet_NaN();
    EXPECT_FLOAT_EQ(nan, nan);
}

TEST(CanaryMustFail, ExpectNearJustOutside)
{
    EXPECT_NEAR(1.0, 1.125 + 1e-9, 0.125);
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

class CanaryTearDownFixture : public ::testing::Test
{
  protected:
    void TearDown() override
    {
        ADD_FAILURE() << "canary failure in TearDown";
    }
};

TEST_F(CanaryTearDownFixture, FailureInTearDown) {}

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

TEST(CanaryMustFailDeathTest, AssertDeathStopsTest)
{
    ASSERT_DEATH(DoNothing(), "");
    RecordProperty("ReachedAfterFatalAssertion", "yes");
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
