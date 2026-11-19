// gate.js (autoresearch, plan 22a): the user script of the corpus pass. bench/gen.py writes it to
// $INPUTS/userscripts/<chunk>/gate.js, after one line that defines AR_GATE, and bench/run gives
// that directory to servoshell as --userscripts, which runs it in every document before the page's own
// scripts.
//
// The timed pages exercise a few flexbox layouts many times. This pass exercises many once: the
// pages of tests/wpt/tests/css/css-flexbox that the attempt's seed drew, in chunks of a few pages,
// each chunk loaded one page after another in a process of its own. On each page it prints a digest of the page's geometry as loaded, then changes the
// page in ways that must relayout it (the body's width, a flex item's size, its flex factors, its
// alignment and order, its text, its container's direction and display) and prints a digest after
// each change. A layout that caches a result past the change that invalidates it shows here.
// eval/check.py compares the "AR1 " lines between the baseline and a candidate, byte for byte.
(function () {
    "use strict";

    if (window.top !== window)
        return;

    var ELEMENTS = 1024;
    var config = window.AR_GATE;
    var path = decodeURIComponent(location.pathname);
    var index = -1;
    for (var i = 0; i < config.pages.length; i++) {
        var tail = "/css-flexbox/" + config.pages[i];
        if (path.slice(-tail.length) === tail) {
            index = i;
            break;
        }
    }
    if (index < 0)
        return;
    var name = config.pages[index];
    var base = location.href.slice(0, location.href.length - encodeURI(name).length);

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

    var state = mixText(mixText(0x811c9dc5, String(config.seed)), name) || 1;
    function draw(n) {
        state ^= state << 13;
        state ^= state >>> 17;
        state ^= state << 5;
        return (state >>> 0) % n;
    }

    function digest() {
        var elements = document.querySelectorAll("*");
        var stride = Math.max(1, Math.ceil(elements.length / ELEMENTS));
        var h = mix(0x811c9dc5, elements.length);
        for (var i = 0; i < elements.length; i += stride) {
            var element = elements[i];
            h = mixRect(h, element.getBoundingClientRect());
            if (element.offsetParent !== undefined) {
                h = mix(h, element.offsetLeft);
                h = mix(h, element.offsetTop);
                h = mix(h, element.offsetWidth);
                h = mix(h, element.offsetHeight);
            }
            h = mix(h, element.clientWidth);
            h = mix(h, element.clientHeight);
            h = mix(h, element.scrollWidth);
            h = mix(h, element.scrollHeight);
        }
        return h;
    }

    function next() {
        if (index + 1 < config.pages.length) {
            location.replace(base + encodeURI(config.pages[index + 1]));
        } else {
            console.log("AR1 END corpus." + config.chunk + " pages=" + config.pages.length);
            window.close();
        }
    }

    function visit() {
        var lines = [];
        function record(label) {
            lines.push("AR1 G " + index + " " + name + " " + label + " h=" + hex(digest()));
        }
        try {
            record("loaded");
            var containers = [];
            var elements = document.querySelectorAll("body *");
            for (var i = 0; i < elements.length && i < 512; i++) {
                var display = getComputedStyle(elements[i]).display;
                if ((display === "flex" || display === "inline-flex") && elements[i].children.length > 0)
                    containers.push(elements[i]);
            }
            if (document.body) {
                document.body.style.width = "83%";
                record("body-width");
            }
            if (containers.length > 0) {
                var container = containers[draw(containers.length)];
                var item = container.children[draw(container.children.length)];
                item.style.width = "37px";
                item.style.height = "29px";
                record("item-size");
                item.style.flexGrow = "2";
                item.style.flexShrink = "3";
                item.style.flexBasis = "41px";
                record("item-flex");
                item.style.alignSelf = "flex-end";
                item.style.order = "-1";
                record("item-align-order");
                item.appendChild(document.createTextNode(" some more words to wrap"));
                record("item-text");
                var direction = getComputedStyle(container).flexDirection;
                container.style.flexDirection = direction.slice(0, 3) === "row" ? "column" : "row";
                record("container-direction");
                container.style.flexWrap = "wrap";
                container.style.width = "211px";
                record("container-wrap");
                var shown = container.style.display;
                container.style.display = "none";
                record("container-hidden");
                container.style.display = shown;
                record("container-shown");
            }
        } catch (e) {
            lines.push("AR1 G " + index + " " + name + " exception " + (e && e.name));
        }
        console.log(lines.join("\n"));
        next();
    }

    var visited = false;
    function once() {
        if (visited)
            return;
        visited = true;
        setTimeout(visit, 0);
    }
    if (document.readyState === "complete")
        once();
    else
        window.addEventListener("load", once);
})();
