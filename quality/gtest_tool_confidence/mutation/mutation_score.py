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
"""Evaluate a Mull mutation-testing-elements report against a threshold.

Detected mutants: Killed, Timeout (the real GoogleTest binary reported a
failure or did not terminate). Undetected: Survived, NoCoverage. Every
undetected mutant is listed and has to be classified in the review
(equivalent mutant / weak test / suspected test-framework malfunction).

Exit code 0 if the score reaches the threshold, 1 otherwise, 2 on bad input.
"""

import argparse
import json
import sys
from pathlib import Path

DETECTED = ("Killed", "Timeout")
UNDETECTED = ("Survived", "NoCoverage")


def evaluate(report):
    counts = {}
    undetected = []
    for path, file_report in sorted(report.get("files", {}).items()):
        for mutant in file_report.get("mutants", []):
            status = mutant.get("status", "Unknown")
            counts[status] = counts.get(status, 0) + 1
            if status in UNDETECTED:
                start = mutant.get("location", {}).get("start", {})
                undetected.append(
                    (path, start.get("line", 0), start.get("column", 0), mutant.get("mutatorName", "?"), status)
                )
    detected = sum(counts.get(s, 0) for s in DETECTED)
    relevant = detected + sum(counts.get(s, 0) for s in UNDETECTED)
    score = 100.0 * detected / relevant if relevant else 0.0
    return score, counts, undetected


def to_markdown(score, threshold, counts, undetected):
    lines = [
        "# Mutation testing result",
        "",
        f"Mutation score: **{score:.1f} %** (threshold {threshold} %)",
        "",
        "| status | mutants |",
        "|---|---|",
    ]
    lines += [f"| {status} | {count} |" for status, count in sorted(counts.items())]
    lines += ["", "## Undetected mutants (to be classified)", ""]
    if undetected:
        lines += ["| file | line:col | mutator | status | classification |", "|---|---|---|---|---|"]
        lines += [f"| {p} | {l}:{c} | {m} | {s} | |" for p, l, c, m, s in undetected]
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--elements", required=True, help="Mull Elements (JSON) report")
    parser.add_argument("--threshold", type=float, default=80.0, help="minimum mutation score in percent")
    parser.add_argument("--markdown", help="write a markdown summary to this file")
    args = parser.parse_args(argv)

    try:
        report = json.loads(Path(args.elements).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"error: cannot read {args.elements}: {error}", file=sys.stderr)
        return 2

    score, counts, undetected = evaluate(report)
    summary = to_markdown(score, args.threshold, counts, undetected)
    if args.markdown:
        Path(args.markdown).write_text(summary, encoding="utf-8")
    print(summary)
    if not counts:
        print("error: report contains no mutants", file=sys.stderr)
        return 2
    return 0 if score >= args.threshold else 1


if __name__ == "__main__":
    sys.exit(main())
