"""
check.py INPUTS ROUNDS BASELINE_OUT CANDIDATE_OUT: the gate (autoresearch, plan 22a).

Locked, and run as the scorer once per attempt, after its rounds (design §8.2 of
pi-autoresearch-serverless). It passes, exiting 0, when in every measured round the candidate laid
out every page exactly as the baseline, the root's build, did.

A round's outputs are one file for each timed page of $INPUTS/pages.txt, <page>.out, and one for
each chunk of the corpus pass in $INPUTS/corpus.txt, corpus.<chunk>.out: a servoshell's stdout. What
counts in one is its lines that start with "AR1 ", digests of the geometry the page could observe
(bench/runner.js, bench/gate.js), in app units, so the comparison is exact:
- the baseline's file must end its page: one "AR1 END" line for it, with the run count or the page
  count the inputs give (a page that failed prints "AR1 FAIL" in its place);
- the candidate's "AR1 " lines must be the baseline's, byte for byte, in the same order.
Every other line (a page's own console output, the "AR0 " times) is left unread. It says why it fails
on stderr, which goes to the owner's check.log alone. It reads outputs as bytes and runs nothing.

The standard library alone.
"""

import json
import sys
from pathlib import Path

PREFIX = b"AR1 "


class Failed(Exception):
    pass


def expected(inputs):
    """Each output file of a round, with the line that ends it."""
    files = {}
    for line in (inputs / "pages.txt").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            page, runs = line.split()
            files[f"{page}.out"] = f"AR1 END {page} runs={runs} ".encode()
    for line in (inputs / "corpus.txt").read_text().splitlines():
        chunk, pages, _first = line.split()
        files[f"corpus.{chunk}.out"] = f"AR1 END corpus.{chunk} pages={pages}".encode()
    return files


def rounds(entries):
    """The measured rounds, which both sides must have run: 0 to n - 1."""
    by_role = {role: sorted(e["round"] for e in entries if e["role"] == role) for role in ("baseline", "candidate")}
    if not by_role["candidate"] or by_role["candidate"] != list(range(len(by_role["candidate"]))):
        raise Failed(f"candidate rounds {by_role['candidate']}")
    if by_role["baseline"] != by_role["candidate"]:
        raise Failed(f"baseline rounds {by_role['baseline']}, candidate rounds {by_role['candidate']}")
    return by_role["candidate"]


def digests(path):
    """The lines of an output file that count."""
    try:
        data = path.read_bytes()
    except OSError as e:
        raise Failed(f"{path.name}: {e.strerror}") from e
    return [line for line in data.split(b"\n") if line.startswith(PREFIX)]


def check_file(name, end, baseline, candidate):
    theirs = digests(baseline / name)
    ended = [line for line in theirs if line.startswith(b"AR1 END ")]
    # A page's END line goes on after its counts; a chunk's is the whole line.
    if len(ended) != 1 or not (ended[0].startswith(end) if end.endswith(b" ") else ended[0] == end):
        raise Failed(f"{name}: the baseline has no line {end.decode()!r}, or several END lines")
    ours = digests(candidate / name)
    if ours != theirs:
        at = next((i for i, (a, b) in enumerate(zip(theirs, ours)) if a != b), min(len(theirs), len(ours)))
        want = theirs[at].decode(errors="replace") if at < len(theirs) else "no more lines"
        got = ours[at].decode(errors="replace") if at < len(ours) else "no more lines"
        raise Failed(f"{name}: line {at} of {len(theirs)} differs: the baseline's {want!r}, the candidate's {got!r}")


def main(argv):
    if len(argv) != 4:
        print("usage: check.py INPUTS ROUNDS BASELINE_OUT CANDIDATE_OUT", file=sys.stderr)
        return 2
    inputs, rounds_json, baseline_out, candidate_out = (Path(a) for a in argv)
    try:
        files = expected(inputs)
        with open(rounds_json) as f:
            measured = rounds(json.load(f))
        for r in measured:
            for name, end in files.items():
                try:
                    check_file(name, end, baseline_out / str(r), candidate_out / str(r))
                except Failed as e:
                    raise Failed(f"round {r}: {e}") from e
            print(f"check: round {r} passes: {len(files)} files", file=sys.stderr)
    except Failed as e:
        print(f"check: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
