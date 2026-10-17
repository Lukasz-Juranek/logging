#!/usr/bin/env bash
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
#
# GoogleTest fault-injection campaign (tool-confidence measure M3).
#
# Injects faults (Mull mutants) into the GoogleTest/gMock sources linked into
# the canary binaries and runs the independent canary checker against every
# mutant. A mutant is detected when the checker fails, i.e. when the faulty
# GoogleTest changes any canary verdict, exit code, test list or reported
# property. The result measures how well the canary suite detects real
# GoogleTest defects. It is a central activity: run it once per GoogleTest
# version or toolchain change, not per module.
#
# Usage:
#   quality/gtest_tool_confidence/mutation/run_gtest_fault_injection.sh \
#       [--threshold 0] [--out gtest_fault_injection_report] [--dry-run]
#
# Environment (defaults match the apt packages clang-19 and Mull-19):
#   MULL_CC          Clang C compiler           (default: clang-19)
#   MULL_PLUGIN      Mull IR frontend plugin    (default: /usr/lib/mull-ir-frontend-19)
#   MULL_RUNNER      Mull runner                (default: mull-runner-19)
#   BAZEL            Bazel executable           (default: bazel)
#   MULL_TIMEOUT_MS  Minimum mutant timeout in ms (default: 20000)
#   MULL_WORKERS     Parallel checker runs      (default: 2)

set -euo pipefail

THRESHOLD=0
OUT="gtest_fault_injection_report"
DRY_RUN=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --threshold) THRESHOLD="$2"; shift 2 ;;
        --out) OUT="$2"; shift 2 ;;
        --dry-run) DRY_RUN="--dry-run"; shift ;;
        -h|--help) sed -n '15,37p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

MULL_CC="${MULL_CC:-clang-19}"
MULL_PLUGIN="${MULL_PLUGIN:-/usr/lib/mull-ir-frontend-19}"
MULL_RUNNER="${MULL_RUNNER:-mull-runner-19}"
BAZEL="${BAZEL:-bazel}"
MULL_TIMEOUT_MS="${MULL_TIMEOUT_MS:-20000}"
MULL_WORKERS="${MULL_WORKERS:-2}"

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
HERE="${WORKSPACE}/quality/gtest_tool_confidence/mutation"
CANARY="//quality/gtest_tool_confidence/canary"
cd "${WORKSPACE}"
mkdir -p "${OUT}"
OUT="$(cd "${OUT}" && pwd)"
CONFIG="${OUT}/mull.yml"
cp "${HERE}/gtest_fault_injection.yml" "${CONFIG}"

STARTUP=(--output_base="${HOME}/.cache/bazel_mull_output_base")
FLAGS=(
    --symlink_prefix=/
    --repo_env=CC="${MULL_CC}"
    --action_env=MULL_CONFIG="${CONFIG}"
    --copt=-O0
    --copt=-g
    # Only the GoogleTest/gMock library sources are instrumented.
    "--per_file_copt=external/googletest[^/]*/google(test|mock)/src/.*\\.cc@-fpass-plugin=${MULL_PLUGIN},-grecord-command-line"
    --strip=never
    --dynamic_mode=off
)
TARGETS=("${CANARY}:gtest_canary_must_fail" "${CANARY}:gtest_canary_must_pass" "${CANARY}:gtest_canary_premature_exit")
"${BAZEL}" "${STARTUP[@]}" build "${FLAGS[@]}" "${TARGETS[@]}"

EXEC_ROOT="$("${BAZEL}" "${STARTUP[@]}" info "${FLAGS[@]}" execution_root 2>/dev/null)"
binary_of() {
    "${BAZEL}" "${STARTUP[@]}" cquery "${FLAGS[@]}" --output=files "$1" 2>/dev/null | head -n 1
}
MUST_FAIL="${EXEC_ROOT}/$(binary_of "${TARGETS[0]}")"
MUST_PASS="${EXEC_ROOT}/$(binary_of "${TARGETS[1]}")"
PREMATURE="${EXEC_ROOT}/$(binary_of "${TARGETS[2]}")"
for b in "${MUST_FAIL}" "${MUST_PASS}" "${PREMATURE}"; do
    [[ -x "${b}" ]] || { echo "canary binary not found: ${b}" >&2; exit 1; }
done

# Mull is used only to discover the mutants compiled into the must-fail binary
# (dry run). The three binaries contain the same GoogleTest mutants, and a
# mutant is activated through an environment variable named after its id, so
# it is active in all of them while the checker runs.
export MULL_CONFIG="${CONFIG}"
# The dry run still executes a warm-up run; the must-fail binary fails by
# design, so a no-op test program is used for discovery.
"${MULL_RUNNER}" \
    --dry-run \
    --test-program="$(command -v true)" \
    --allow-surviving \
    --no-output \
    --reporters=Elements \
    --report-dir="${OUT}" \
    --report-name=gtest_mutants \
    "${MUST_FAIL}" > "${OUT}/gtest_mutants.log"

[[ -n "${DRY_RUN}" ]] && exit 0

# The faults are executed by fault_injection_driver.py, not by mull-runner:
# mull-runner's verdicts for an external --test-program were found unreliable.
export PYTHONPATH="${WORKSPACE}"
python3 "${HERE}/fault_injection_driver.py" \
    --mutants "${OUT}/gtest_mutants.json" \
    --output "${OUT}/gtest_fault_injection.json" \
    --workers "${MULL_WORKERS}" \
    --timeout "$((MULL_TIMEOUT_MS / 1000))" \
    -- python3 "${WORKSPACE}/quality/gtest_tool_confidence/canary/check_gtest_canaries.py" \
    "${WORKSPACE}/quality/gtest_tool_confidence/canary/canary_expectations.json" \
    "${MUST_FAIL}" "${MUST_PASS}" "${PREMATURE}" | tee "${OUT}/gtest_fault_injection.log"

python3 "${HERE}/mutation_score.py" \
    --elements "${OUT}/gtest_fault_injection.json" \
    --threshold "${THRESHOLD}" \
    --markdown "${OUT}/gtest_fault_injection.md"
