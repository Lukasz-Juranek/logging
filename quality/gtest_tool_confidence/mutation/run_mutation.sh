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
# Mutation run with Mull for the GoogleTest tool-confidence argument.
#
# Builds the given cc_test with Clang and the Mull IR frontend (only the scope's
# production sources are mutated), runs the real GoogleTest binary under
# mull-runner and evaluates the mutation score against a threshold.
#
# Usage:
#   quality/gtest_tool_confidence/mutation/run_mutation.sh \
#       --target //score/mw/log/detail/wait_free_producer_queue:unit_test \
#       --scope score/mw/log/detail/wait_free_producer_queue \
#       [--threshold 80] [--out mutation_report]
#
# Environment (defaults match the apt packages clang-19 and Mull-19):
#   MULL_CC        Clang C compiler           (default: clang-19)
#   MULL_PLUGIN    Mull IR frontend plugin    (default: /usr/lib/mull-ir-frontend-19)
#   MULL_RUNNER    Mull runner                (default: mull-runner-19)
#   BAZEL          Bazel executable           (default: bazel)
#   MULL_TIMEOUT_MS  Baseline / minimum mutant timeout in ms (default: 60000)

set -euo pipefail

TARGET=""
SCOPE=""
THRESHOLD=80
OUT="mutation_report"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --target) TARGET="$2"; shift 2 ;;
        --scope) SCOPE="$2"; shift 2 ;;
        --threshold) THRESHOLD="$2"; shift 2 ;;
        --out) OUT="$2"; shift 2 ;;
        -h|--help) sed -n '15,32p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [[ -z "${TARGET}" || -z "${SCOPE}" ]]; then
    echo "--target and --scope are required" >&2
    exit 2
fi

MULL_CC="${MULL_CC:-clang-19}"
MULL_PLUGIN="${MULL_PLUGIN:-/usr/lib/mull-ir-frontend-19}"
MULL_RUNNER="${MULL_RUNNER:-mull-runner-19}"
BAZEL="${BAZEL:-bazel}"
MULL_TIMEOUT_MS="${MULL_TIMEOUT_MS:-60000}"

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
HERE="${WORKSPACE}/quality/gtest_tool_confidence/mutation"
cd "${WORKSPACE}"
mkdir -p "${OUT}"
OUT="$(cd "${OUT}" && pwd)"

# Mull configuration: base operators/excludes plus the requested scope.
CONFIG="${OUT}/mull.yml"
cp "${HERE}/mull.yml" "${CONFIG}"
printf 'includePaths:\n  - "%s/.*"\n' "${SCOPE//./\\.}" >> "${CONFIG}"

SCOPE_REGEX="${SCOPE//./\\.}/.*\\.cpp,-.*_test\\.cpp"

# A separate output base keeps the instrumented build away from the normal one,
# and --symlink_prefix=/ keeps it from replacing the workspace's bazel-*
# convenience symlinks. The host platform with the auto-configured local
# toolchain (CC) is used, so no S-CORE GCC toolchain is involved.
STARTUP=(--output_base="${HOME}/.cache/bazel_mull_output_base")
FLAGS=(
    --symlink_prefix=/
    --repo_env=CC="${MULL_CC}"
    --action_env=MULL_CONFIG="${CONFIG}"
    --copt=-O0
    --copt=-g
    --per_file_copt="${SCOPE_REGEX}@-fpass-plugin=${MULL_PLUGIN},-grecord-command-line"
    --strip=never
    # Link the scope's libraries statically: mull-runner reads the mutants from
    # the test executable, not from shared libraries.
    --dynamic_mode=off
)
"${BAZEL}" "${STARTUP[@]}" build "${FLAGS[@]}" "${TARGET}"

EXEC_ROOT="$("${BAZEL}" "${STARTUP[@]}" info "${FLAGS[@]}" execution_root 2>/dev/null)"
BINARY_REL="$("${BAZEL}" "${STARTUP[@]}" cquery "${FLAGS[@]}" --output=files "${TARGET}" 2>/dev/null | head -n 1)"
BINARY="${EXEC_ROOT}/${BINARY_REL}"
if [[ -z "${BINARY_REL}" || ! -x "${BINARY}" ]]; then
    echo "test binary for ${TARGET} not found (got '${BINARY}')" >&2
    exit 1
fi

REPORT_NAME="$(echo "${TARGET}" | tr '/:' '__' | sed 's/^_*//')"
RUNFILES="${BINARY}.runfiles"
(
    if [[ -d "${RUNFILES}/_main" ]]; then
        cd "${RUNFILES}/_main"
        export RUNFILES_DIR="${RUNFILES}"
    fi
    export MULL_CONFIG="${CONFIG}"
    # The runner's default baseline timeout (3 s) is shorter than many unit
    # tests; a mutant's timeout is max(10 x baseline, --minimum-timeout).
    "${MULL_RUNNER}" \
        --timeout="${MULL_TIMEOUT_MS}" \
        --minimum-timeout="${MULL_TIMEOUT_MS}" \
        --allow-surviving \
        --reporters=Elements \
        --reporters=IDE \
        --ide-reporter-show-killed \
        --report-dir="${OUT}" \
        --report-name="${REPORT_NAME}" \
        "${BINARY}" | tee "${OUT}/${REPORT_NAME}.log"
)

python3 "${HERE}/mutation_score.py" \
    --elements "${OUT}/${REPORT_NAME}.json" \
    --threshold "${THRESHOLD}" \
    --markdown "${OUT}/${REPORT_NAME}.md"
