// runner.js (autoresearch, plan 22a): the fixed-work stand-in for Blink's perf_tests/resources/runner.js.
// bench/gen.py writes it to $INPUTS/site/resources/runner.js, after one line that defines AR_CONFIG,
// so the benchmark pages, copied unchanged, load it as their ../resources/runner.js.
//
// Blink's runner calls a page's run() for 750 ms at a time and reports runs per second, from the
// page's own clock. This one calls run() exactly AR_CONFIG.pages[<page>] times in one task, and the
// sandbox times the process: the work is fixed, and the page reports no time that counts.
//
// What it prints, on stdout through console.log, is what eval/check.py compares between the baseline
// and a candidate, byte for byte: every line that starts with "AR1 ".
// - Each forceLayout() of the loop reads body.offsetHeight, as Blink's does, then the bounding rect
//   of one element drawn by the attempt's seed: both go into a rolling hash, so every layout of the
//   loop is observed, not just the last.
// - On three runs (the first, the last and one drawn by the seed), the first PROBE_CALLS forced
//   layouts each take a digest of up to PROBE_ELEMENTS elements: four pages end every run back in
//   their block state, so their flex layout shows only inside a run.
// - After the loop, a digest of up to FINAL_ELEMENTS elements, with used style values and hit tests.
// "AR0 " lines are for the owner alone (times, counts) and are compared by nothing.
// Geometry is hashed in app units, 1/60 px, which is what Servo's layout computes in.
(function () {
    "use strict";

    var PROBE_CALLS = 4;
    var PROBE_ELEMENTS = 256;
    var FINAL_ELEMENTS = 2048;

    var config = window.AR_CONFIG;
    var page = location.pathname.replace(/^.*\//, "").replace(/\.html$/, "");
    var runs = config.pages[page];
    var lines = [];
    var started = false;
    var finished = false;

    function finish() {
        if (finished)
            return;
        finished = true;
        console.log(lines.join("\n"));
        window.close();
    }

    function fail(reason) {
        lines = ["AR1 FAIL " + page + " " + reason];
        finish();
    }

    window.addEventListener("error", function (event) {
        fail("error: " + event.message);
    });

    // FNV-1a over an integer's two halves.
    function mix(h, v) {
        v = v | 0;
        h = Math.imul(h ^ (v & 0xffff), 0x01000193);
        return Math.imul(h ^ (v >>> 16), 0x01000193);
    }

    function mixText(h, text) {
        for (var i = 0; i < text.length; i++)
            h = Math.imul(h ^ text.charCodeAt(i), 0x01000193);
        return mix(h, text.length);
    }

    function au(px) {
        return Math.round(px * 60);
    }

    function mixRect(h, r) {
        h = mix(h, au(r.left));
        h = mix(h, au(r.top));
        h = mix(h, au(r.width));
        return mix(h, au(r.height));
    }

    function hex(h) {
        return ("0000000" + (h >>> 0).toString(16)).slice(-8);
    }

    // The attempt's own stream, for what the harness draws: xorshift32, seeded from the seed's text.
    var state = mixText(0x811c9dc5, String(config.seed)) || 1;
    function draw(n) {
        state ^= state << 13;
        state ^= state >>> 17;
        state ^= state << 5;
        return (state >>> 0) % n;
    }

    // Blink's runner replaces Math.random by this generator, so that a page's content is the same
    // on every load: copied as it is.
    var PerfTestRunner = window.PerfTestRunner = {};
    PerfTestRunner.randomSeed = PerfTestRunner.initialRandomSeed = 49734321;
    PerfTestRunner.resetRandomSeed = function () {
        PerfTestRunner.randomSeed = PerfTestRunner.initialRandomSeed;
    };
    PerfTestRunner.random = Math.random = function () {
        var randomSeed = PerfTestRunner.randomSeed;
        randomSeed = ((randomSeed + 0x7ed55d16) + (randomSeed << 12)) & 0xffffffff;
        randomSeed = ((randomSeed ^ 0xc761c23c) ^ (randomSeed >>> 19)) & 0xffffffff;
        randomSeed = ((randomSeed + 0x165667b1) + (randomSeed << 5)) & 0xffffffff;
        randomSeed = ((randomSeed + 0xd3a2646c) ^ (randomSeed << 9)) & 0xffffffff;
        randomSeed = ((randomSeed + 0xfd7046c5) + (randomSeed << 3)) & 0xffffffff;
        randomSeed = ((randomSeed ^ 0xb55a4f09) ^ (randomSeed >>> 16)) & 0xffffffff;
        PerfTestRunner.randomSeed = randomSeed;
        return (randomSeed & 0xfffffff) / 0x10000000;
    };

    function mixElement(h, element) {
        h = mixRect(h, element.getBoundingClientRect());
        if (element.offsetParent !== undefined) {
            h = mix(h, element.offsetLeft);
            h = mix(h, element.offsetTop);
            h = mix(h, element.offsetWidth);
            h = mix(h, element.offsetHeight);
        }
        h = mix(h, element.clientLeft);
        h = mix(h, element.clientTop);
        h = mix(h, element.clientWidth);
        h = mix(h, element.clientHeight);
        h = mix(h, element.scrollWidth);
        h = mix(h, element.scrollHeight);
        var rects = element.getClientRects();
        h = mix(h, rects.length);
        for (var i = 0; i < rects.length && i < 4; i++)
            h = mixRect(h, rects[i]);
        return h;
    }

    // Up to `limit` of the document's elements, evenly spaced in tree order.
    function digest(limit, deep) {
        var elements = document.querySelectorAll("*");
        var stride = Math.max(1, Math.ceil(elements.length / limit));
        var h = mix(0x811c9dc5, elements.length);
        for (var i = 0; i < elements.length; i += stride) {
            h = mixElement(h, elements[i]);
            if (deep && (i / stride) % 16 === 0) {
                var style = getComputedStyle(elements[i]);
                h = mixText(h, style.width);
                h = mixText(h, style.height);
                h = mixText(h, style.top);
                h = mixText(h, style.left);
            }
        }
        if (deep) {
            var index = new Map();
            for (var k = 0; k < elements.length; k++)
                index.set(elements[k], k);
            for (var y = 0; y < 6; y++) {
                for (var x = 0; x < 8; x++) {
                    var hit = document.elementFromPoint(64 + x * 128, 64 + y * 128);
                    h = mix(h, hit && index.has(hit) ? index.get(hit) : -1);
                }
            }
        }
        return h;
    }

    var measuring = false;
    var witnesses = [];
    var roll = 0x811c9dc5;
    var calls = 0;
    var run = 0;
    var probeCalls = 0;

    PerfTestRunner.forceLayout = function (doc) {
        doc = doc || document;
        var root = doc.body || doc.documentElement;
        var height = root ? root.offsetHeight : 0;
        if (!measuring)
            return;
        calls++;
        roll = mix(roll, height);
        if (witnesses.length > 0)
            roll = mixRect(roll, witnesses[draw(witnesses.length)].getBoundingClientRect());
        if (probeCalls > 0) {
            probeCalls--;
            lines.push("AR1 P " + page + " run=" + run + " call=" + calls + " h=" + hex(digest(PROBE_ELEMENTS, false)));
        }
    };

    function measure(test) {
        try {
            witnesses = Array.prototype.slice.call(document.querySelectorAll("*"));
            var probed = {};
            probed[0] = probed[runs - 1] = true;
            if (runs > 2)
                probed[1 + draw(runs - 2)] = true;
            var begin = performance.now();
            measuring = true;
            for (run = 0; run < runs; run++) {
                probeCalls = probed[run] ? PROBE_CALLS : 0;
                test.run();
            }
            measuring = false;
            var middle = performance.now();
            var final = digest(FINAL_ELEMENTS, true);
            var end = performance.now();
            lines.push("AR1 END " + page + " runs=" + runs + " calls=" + calls + " roll=" + hex(roll) + " final=" + hex(final));
            lines.push("AR0 TIME " + page + " loop_ms=" + (middle - begin).toFixed(1) + " digest_ms=" + (end - middle).toFixed(1) +
                " elements=" + witnesses.length);
        } catch (e) {
            fail("exception: " + e);
            return;
        }
        finish();
    }

    PerfTestRunner.measureRunsPerSecond = function (test) {
        if (started) {
            fail("measureRunsPerSecond called twice");
            return;
        }
        started = true;
        if (!(runs > 0) || !test || typeof test.run !== "function") {
            fail("no run count or no run function");
            return;
        }
        var go = function () {
            setTimeout(function () { measure(test); }, 0);
        };
        if (document.readyState === "complete")
            go();
        else
            window.addEventListener("load", go);
    };

    PerfTestRunner.now = function () { return performance.now(); };
    PerfTestRunner.gc = function () {};
    PerfTestRunner.log = PerfTestRunner.logInfo = function () {};

    // The flexbox pages use nothing else; a page that does is not one this harness times.
    ["measureTime", "measureValue", "measureFrameTime", "measureInnerRAFTime", "measurePageLoadTime",
        "startMeasureValuesAsync", "measureValueAsync", "startMeasureValuesInWorker"].forEach(function (name) {
        PerfTestRunner[name] = function () { fail("unsupported: PerfTestRunner." + name); };
    });
})();
