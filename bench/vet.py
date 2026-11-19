"""
vet.py SERVOSHELL [--flexbox DIR] [--runs N] [--chunk N]: which pages can be in the corpus.

Not a step of any attempt: the owner's tool, which made bench/corpus.txt (autoresearch, plan 22a),
and makes it again when the root's Servo or its copy of the web platform tests changes.

A page of tests/wpt/tests/css/css-flexbox is fit for the corpus pass (bench/gate.js) when, loaded
from file:// in a headless servoshell with no network:
- it is a test, not a reference, and has nothing that makes its geometry depend on time or on
  another document (the words of SKIP);
- the pass gets through it: it loads, and the next page follows;
- its lines are the same on every one of N runs, and none reports an exception.
It prints the fit pages on stdout, one per line, sorted, and why it left each other out on stderr.

The standard library alone.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TREE = Path(__file__).resolve().parent.parent
GATE = TREE / "bench" / "gate.js"

# A page with one of these is left out unread: timers, animations, frames and plugins, navigation.
SKIP = [
    "<iframe", "<frame", "<object", "<embed", "<video", "<audio", "<canvas", "http-equiv", "reftest-wait",
    "test-wait", "settimeout", "setinterval", "requestanimationframe", "animation", "transition", "@keyframes",
    "window.open", "location.", "document.write", "scrollto", "scrollintoview", "focus(",
]


def candidates(flexbox):
    """The directory's own pages that are tests and have none of SKIP's words."""
    fit, left = [], {}
    for path in sorted(flexbox.glob("*.html")):
        name = path.name
        if name.endswith(("-ref.html", "-notref.html", "-expected.html")) or "-ref-" in name:
            left[name] = "a reference"
            continue
        if not name.isascii() or any(c.isspace() for c in name):
            left[name] = "its name"
            continue
        text = path.read_text(errors="replace").lower()
        found = next((word for word in SKIP if word in text), None)
        if found is not None:
            left[name] = f"has {found!r}"
        else:
            fit.append(name)
    return fit, left


def visit(servoshell, flexbox, pages, seed):
    """One pass over `pages`: each page's lines, by its index, and whether the pass ended."""
    with tempfile.TemporaryDirectory() as scratch:
        scripts = Path(scratch) / "userscripts"
        scripts.mkdir()
        config = json.dumps({"seed": str(seed), "chunk": 0, "pages": pages}, sort_keys=True)
        (scripts / "gate.js").write_text(f"var AR_GATE = {config};\n{GATE.read_text()}")
        argv = [
            servoshell, "--headless", "--hard-fail", "--window-size", "1024x768", "--device-pixel-ratio", "1",
            "--temporary-storage", "--config-dir", str(Path(scratch) / "config"),
            "--pref", "dom_allow_scripts_to_close_windows", "--pref", "perf_thread_boost_enabled=false",
            "--userscripts", str(scripts), f"file://{flexbox}/{pages[0]}",
        ]  # fmt: skip
        try:
            out = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20 + 2 * len(pages)).stdout
        except subprocess.TimeoutExpired as e:
            out = e.stdout or b""
    lines = {}
    ended = False
    for line in out.decode(errors="replace").splitlines():
        if line.startswith("AR1 G "):
            lines.setdefault(int(line.split()[2]), []).append(line.split(" ", 4)[4])
        elif line.startswith("AR1 END corpus."):
            ended = True
    return lines, ended


def passes(servoshell, flexbox, pages, seed, left):
    """`pages` without those a pass stops at, and their lines by name."""
    while pages:
        lines, ended = visit(servoshell, flexbox, pages, seed)
        if ended:
            return pages, {page: lines.get(i, []) for i, page in enumerate(pages)}
        # The pass stopped on the page after the last one that printed.
        stuck = max(lines, default=-1) + 1
        if stuck >= len(pages):
            stuck = len(pages) - 1
        left[pages[stuck]] = "the pass stops there"
        pages = pages[:stuck] + pages[stuck + 1 :]
    return [], {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("servoshell")
    parser.add_argument("--flexbox", type=Path, default=TREE / "tests" / "wpt" / "tests" / "css" / "css-flexbox")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--chunk", type=int, default=25)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    flexbox = args.flexbox.resolve()

    pages, left = candidates(flexbox)
    fit = []
    for start in range(0, len(pages), args.chunk):
        chunk, first = passes(args.servoshell, flexbox, pages[start : start + args.chunk], args.seed, left)
        stable = set(chunk)
        for _ in range(args.runs - 1):
            again, lines = passes(args.servoshell, flexbox, chunk, args.seed, left)
            for page in chunk:
                if page in stable and (page not in again or lines[page] != first[page]):
                    stable.discard(page)
                    left.setdefault(page, "its lines change from run to run")
        for page in chunk:
            if page not in stable:
                continue
            if not first[page] or not first[page][0].startswith("loaded "):
                left[page] = "no line for the page as loaded"
            elif any("exception" in line for line in first[page]):
                left[page] = "an exception in the pass"
            else:
                fit.append(page)
        print(f"vet: {start + len(pages[start : start + args.chunk])}/{len(pages)} pages, {len(fit)} fit", file=sys.stderr)
    for page, why in sorted(left.items()):
        print(f"vet: left out {page}: {why}", file=sys.stderr)
    print("\n".join(sorted(fit)))


if __name__ == "__main__":
    main()
