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
"""Run the canary checker against every GoogleTest fault, one at a time.

Input is the Mull Elements report of a dry run (mutants discovered, none
executed). Each Mull mutant is compiled into the binaries and is activated by
setting an environment variable named after the mutant id to "1". For every
mutant this driver runs the checker command in a clean temporary directory
with only that mutant active and records:

* Killed   - the checker failed (the faulty GoogleTest was detected),
* Timeout  - the checker did not finish (counts as detected),
* Survived - the checker passed (the fault was not detected).

mull-runner is deliberately not used to execute the checker: its verdicts
for an external --test-program were found to be unreliable (mutants reported
as killed that the checker does not detect when run directly).

Before the campaign, the checker must pass without any active mutant
(baseline); otherwise every mutant would look detected.

Output is an Elements-format JSON with the statuses filled in, which
mutation_score.py evaluates.
"""

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run_checker(command, mutant_id, timeout):
    """Return 'Killed', 'Timeout' or 'Survived' for one mutant (None = baseline)."""
    with tempfile.TemporaryDirectory(prefix="gtest_fi_") as tmp:
        env = dict(os.environ)
        env["TMPDIR"] = tmp
        if mutant_id is not None:
            env[mutant_id] = "1"
        try:
            completed = subprocess.run(
                command,
                cwd=tmp,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return "Timeout"
    return "Survived" if completed.returncode == 0 else "Killed"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mutants", required=True, help="Mull Elements JSON from a --dry-run")
    parser.add_argument("--output", required=True, help="Elements JSON with the measured statuses")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds per checker run")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="checker command (after --)")
    args = parser.parse_args(argv)

    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("checker command missing")

    report = json.loads(Path(args.mutants).read_text(encoding="utf-8"))
    mutants = [m for f in report.get("files", {}).values() for m in f.get("mutants", [])]
    if not mutants:
        print("error: no mutants in the dry-run report", file=sys.stderr)
        return 2

    baseline = run_checker(command, None, args.timeout)
    if baseline != "Survived":
        print(f"error: checker does not pass without faults (baseline: {baseline})", file=sys.stderr)
        return 2

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_checker, command, m["id"], args.timeout): m for m in mutants}
        for done, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            futures[future]["status"] = future.result()
            if done % 50 == 0 or done == len(mutants):
                print(f"{done}/{len(mutants)} mutants", flush=True)

    Path(args.output).write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
