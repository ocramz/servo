"""
selftest.py [--trials N] [--seed S]: the harness checked against itself (autoresearch, plan 22a).

Not a step of any attempt: the owner's test, to run after a change to bench/ or eval/. It needs no
Servo. With bench/gen.py's real inputs for random seeds, it makes the outputs a round would leave,
then checks properties of eval/check.py, each over random cases:
- identical outputs pass, whatever each side prints besides its "AR1 " lines;
- any change to what counts fails: a digest's digit, a line dropped, doubled or moved, a page that
  failed or didn't end, a file or a round missing, a wrong run count, or rounds one side didn't run;
and of bench/gen.py: the same seed gives the same inputs, the corpus pass has its pages in chunks,
each with its user script, and the timed pages have their run counts.
It exits 0 when all hold, and says which didn't on stderr.

The standard library alone.
"""

import argparse
import json
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EVAL = Path(__file__).resolve().parent
TREE = EVAL.parent
ROUNDS = 3


def python(script, *args):
    return subprocess.run([sys.executable, "-I", str(script), *map(str, args)], capture_output=True, text=True)


def generate(seed, inputs):
    done = python(TREE / "bench" / "gen.py", seed, inputs)
    if done.returncode != 0:
        raise SystemExit(f"selftest: gen.py failed: {done.stderr}")


def listing(root):
    """Every file under `root`, with its bytes."""
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def digest(rng):
    return f"{rng.getrandbits(32):08x}"


def noise(rng):
    """A line that doesn't count: a page's own output, a time."""
    return rng.choice([
        f"AR0 TIME page loop_ms={rng.random() * 2000:.1f} digest_ms={rng.random() * 100:.1f} elements={rng.randrange(30000)}",
        f"console says {rng.getrandbits(40):x}",
        "",
        " AR1 not at the start of its line",
    ])  # fmt: skip


def round_outputs(inputs, rng):
    """One round's files, as lists of lines, as a servoshell of the root would print them."""
    files = {}
    for line in (inputs / "pages.txt").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        page, runs = line.split()
        lines = [f"AR1 P {page} run={rng.randrange(int(runs))} call={n} h={digest(rng)}" for n in range(1, 13)]
        lines.append(f"AR1 END {page} runs={runs} calls={rng.randrange(1, 10**6)} roll={digest(rng)} final={digest(rng)}")
        files[f"{page}.out"] = lines
    for line in (inputs / "corpus.txt").read_text().splitlines():
        chunk, pages, first = line.split()
        lines = [f"AR1 G {i} {first} {label} h={digest(rng)}" for i in range(int(pages)) for label in ("loaded", "body-width")]
        lines.append(f"AR1 END corpus.{chunk} pages={pages}")
        files[f"corpus.{chunk}.out"] = lines
    return files


def with_noise(lines, rng):
    """The same lines that count, among others that don't."""
    out = []
    for line in lines:
        out.extend(noise(rng) for _ in range(rng.randrange(3)))
        out.append(line)
    out.extend(noise(rng) for _ in range(rng.randrange(3)))
    return out


def write(root, role, rounds):
    for r, files in rounds.items():
        directory = root / role / str(r)
        directory.mkdir(parents=True)
        for name, lines in files.items():
            (directory / name).write_text("".join(f"{line}\n" for line in lines))


def gate(inputs, baseline, candidate, entries, scratch):
    """check.py's exit status on these outputs."""
    root = Path(tempfile.mkdtemp(dir=scratch))
    write(root, "baseline", baseline)
    write(root, "candidate", candidate)
    (root / "rounds.json").write_text(json.dumps(entries))
    done = python(EVAL / "check.py", inputs, root / "rounds.json", root / "baseline", root / "candidate")
    shutil.rmtree(root)
    return done.returncode, done.stderr.strip()


def entries_of(rounds):
    return [{"role": role, "round": r, "wall_ms": 20000} for r in rounds for role in ("baseline", "candidate")]


def plant(candidate, baseline, entries, rng):
    """One change to what counts, in place: its name."""
    r = rng.choice(sorted(candidate))
    name = rng.choice(sorted(candidate[r]))
    lines = candidate[r][name]
    counted = [i for i, line in enumerate(lines) if line.startswith("AR1 ")]
    kind = rng.choice(["digit", "drop", "double", "move", "fail", "no end", "file", "round", "runs", "rounds", "baseline"])
    if kind == "digit":
        i = rng.choice(counted)
        at = lines[i].rindex("=") + 1 + rng.randrange(8) if "h=" in lines[i] or "final=" in lines[i] else len(lines[i]) - 1
        lines[i] = lines[i][:at] + ("0" if lines[i][at] != "0" else "1") + lines[i][at + 1 :]
    elif kind == "drop":
        del lines[rng.choice(counted)]
    elif kind == "double":
        i = rng.choice(counted)
        lines.insert(i, lines[i])
    elif kind == "move":
        i, j = counted[0], counted[-1]
        lines[i], lines[j] = lines[j], lines[i]
    elif kind == "fail":
        lines.insert(rng.randrange(len(lines) + 1), "AR1 FAIL page exception: Error")
    elif kind == "no end":
        candidate[r][name] = [line for line in lines if not line.startswith("AR1 END ")]
    elif kind == "file":
        del candidate[r][name]
    elif kind == "round":
        del candidate[r]
    elif kind == "runs":
        end = next(i for i in counted if lines[i].startswith("AR1 END "))
        lines[end] = lines[end].replace("=", "=1", 1)
    elif kind == "rounds":
        entries[:] = [e for e in entries if not (e["role"] == "candidate" and e["round"] == max(candidate))]
    else:
        # The baseline's own page didn't end, and the candidate's is the same: still no pass.
        baseline[r][name] = [line for line in baseline[r][name] if not line.startswith("AR1 END ")]
        candidate[r][name] = list(baseline[r][name])
    return f"{kind} in round {r}, {name}"


def check_gen(inputs, seed, scratch, failures):
    again = Path(tempfile.mkdtemp(dir=scratch)) / "inputs"
    generate(seed, again)
    if listing(inputs) != listing(again):
        failures.append(f"gen.py: seed {seed} gave two different inputs")
    timed = [line.split() for line in (TREE / "bench" / "pages.txt").read_text().splitlines() if line.strip() and not line.startswith("#")]
    runner = (inputs / "site" / "resources" / "runner.js").read_text()
    config = json.loads(runner.split("\n", 1)[0].removeprefix("var AR_CONFIG = ").removesuffix(";"))
    if config != {"seed": str(seed), "pages": {page: int(runs) for page, runs in timed}}:
        failures.append(f"gen.py: seed {seed}: runner.js's configuration isn't pages.txt's and the seed")
    for page, _ in timed:
        if not (inputs / "site" / "layout" / f"{page}.html").is_file():
            failures.append(f"gen.py: no page {page}")
    listed = {line.strip() for line in (TREE / "bench" / "corpus.txt").read_text().splitlines() if line.strip() and not line.startswith("#")}
    drawn = []
    for line in (inputs / "corpus.txt").read_text().splitlines():
        chunk, pages, first = line.split()
        gate_js = (inputs / "userscripts" / chunk / "gate.js").read_text()
        config = json.loads(gate_js.split("\n", 1)[0].removeprefix("var AR_GATE = ").removesuffix(";"))
        if config["chunk"] != int(chunk) or len(config["pages"]) != int(pages) or config["pages"][0] != first or config["seed"] != str(seed):
            failures.append(f"gen.py: seed {seed}: chunk {chunk}'s user script isn't its line of corpus.txt")
        drawn.extend(config["pages"])
    if len(set(drawn)) != len(drawn) or not set(drawn) <= listed or len(drawn) != min(150, len(listed)):
        failures.append(f"gen.py: seed {seed}: the corpus pass isn't 150 different pages of corpus.txt")
    if any(not (inputs / "wpt" / "css" / "css-flexbox" / page).is_file() for page in drawn):
        failures.append(f"gen.py: seed {seed}: a drawn page isn't in the inputs")
    if (inputs / "run").read_bytes() != (TREE / "bench" / "run").read_bytes():
        failures.append("gen.py: the driver isn't bench/run")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=150)
    parser.add_argument("--seed", type=int, default=random.SystemRandom().getrandbits(64))
    args = parser.parse_args()
    rng = random.Random(args.seed)
    failures = []
    with tempfile.TemporaryDirectory() as scratch:
        scratch = Path(scratch)
        for _ in range(3):
            seed = rng.getrandbits(64)
            inputs = Path(tempfile.mkdtemp(dir=scratch)) / "inputs"
            generate(seed, inputs)
            check_gen(inputs, seed, scratch, failures)
        for trial in range(args.trials):
            baseline = {r: round_outputs(inputs, rng) for r in range(ROUNDS)}
            same = {r: {name: with_noise(lines, rng) for name, lines in files.items()} for r, files in baseline.items()}
            noisy = {r: {name: with_noise(lines, rng) for name, lines in files.items()} for r, files in baseline.items()}
            status, said = gate(inputs, noisy, same, entries_of(baseline), scratch)
            if status != 0:
                failures.append(f"trial {trial}: identical outputs fail: {said}")
            entries = entries_of(baseline)
            planted = plant(same, noisy, entries, rng)
            status, said = gate(inputs, noisy, same, entries, scratch)
            if status != 1:
                failures.append(f"trial {trial}: {planted}: exit {status}, not 1: {said}")
    for failure in failures:
        print(f"selftest: {failure}", file=sys.stderr)
    print(f"selftest: seed {args.seed}, {args.trials} trials, {len(failures)} failures", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
