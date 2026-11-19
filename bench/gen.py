"""
gen.py SEED INPUTS: an attempt's inputs (autoresearch, plan 22a).

Locked, and run as the scorer from the locked tree, once per attempt (design §8.2 of
pi-autoresearch-serverless). Both sides of every pair then run on the same $INPUTS:

  pages.txt             the timed pages and their run counts, bench/pages.txt
  site/layout/*.html    the timed pages, copied unchanged from tests/blink_perf_tests
  site/resources/runner.js
                        bench/runner.js, after a line that gives it the run counts and the seed,
                        where the pages look for Blink's runner
  corpus.txt            the corpus pass: CORPUS_PAGES of bench/corpus.txt drawn by the seed, in
                        chunks of CORPUS_CHUNK, one line a chunk: its number, how many pages it has
                        and its first page
  wpt/css/css-flexbox/  tests/wpt/tests/css/css-flexbox, whole: the corpus pages and what they load
  userscripts/<chunk>/gate.js
                        bench/gate.js, after a line that gives it the chunk's pages and the seed
  run                   bench/run, the driver: `run` is `sh $INPUTS/run $BUILD $INPUTS $OUTPUTS`

The standard library alone.
"""

import json
import random
import shutil
import sys
from pathlib import Path

# The pages of one corpus pass, and of each of its processes. A process's resident set grows with
# the pages it has loaded: at 10 it stays under the largest timed page's, so that the round's peak
# memory, its hungriest process's, is a timed page's (plan 22a).
CORPUS_PAGES = 150
CORPUS_CHUNK = 10

TREE = Path(__file__).resolve().parent.parent
BENCH = TREE / "bench"
LAYOUT = TREE / "tests" / "blink_perf_tests" / "perf_tests" / "layout"
FLEXBOX = TREE / "tests" / "wpt" / "tests" / "css" / "css-flexbox"


def pages(text):
    """The timed pages of a pages.txt, in order, as (name, run count)."""
    found = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, runs = line.split()
        if int(runs) < 1:
            raise ValueError(f"pages.txt: {name} runs {runs} times")
        found.append((name, int(runs)))
    if not found or len({name for name, _ in found}) != len(found):
        raise ValueError("pages.txt: no page, or one twice")
    return found


def corpus(text):
    """The pages of a corpus.txt, in order."""
    found = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if len(set(found)) != len(found):
        raise ValueError("corpus.txt: a page twice")
    return found


def with_config(name, config, script):
    """A script after the line that defines its configuration."""
    return f"var {name} = {json.dumps(config, sort_keys=True)};\n{script}"


def main(argv):
    if len(argv) != 3:
        print("usage: gen.py SEED INPUTS", file=sys.stderr)
        return 2
    seed = int(argv[1])
    inputs = Path(argv[2])

    timed = pages((BENCH / "pages.txt").read_text())
    inputs.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BENCH / "pages.txt", inputs / "pages.txt")
    (inputs / "site" / "layout").mkdir(parents=True)
    (inputs / "site" / "resources").mkdir()
    for name, _ in timed:
        shutil.copyfile(LAYOUT / f"{name}.html", inputs / "site" / "layout" / f"{name}.html")
    # The seed as text: a 64-bit integer is no exact JavaScript number.
    (inputs / "site" / "resources" / "runner.js").write_text(
        with_config("AR_CONFIG", {"seed": str(seed), "pages": dict(timed)}, (BENCH / "runner.js").read_text())
    )

    listed = corpus((BENCH / "corpus.txt").read_text())
    drawn = random.Random(seed).sample(listed, min(CORPUS_PAGES, len(listed)))
    shutil.copytree(FLEXBOX, inputs / "wpt" / "css" / "css-flexbox")
    gate = (BENCH / "gate.js").read_text()
    chunks = [drawn[i : i + CORPUS_CHUNK] for i in range(0, len(drawn), CORPUS_CHUNK)]
    for number, chunk in enumerate(chunks):
        scripts = inputs / "userscripts" / str(number)
        scripts.mkdir(parents=True)
        (scripts / "gate.js").write_text(with_config("AR_GATE", {"seed": str(seed), "chunk": number, "pages": chunk}, gate))
    (inputs / "corpus.txt").write_text("".join(f"{number} {len(chunk)} {chunk[0]}\n" for number, chunk in enumerate(chunks)))

    shutil.copyfile(BENCH / "run", inputs / "run")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
