#!/usr/bin/env python3
"""Import an Excalidraw drawing (.excalidraw / .json export) into a live-panel `excalidraw` view config.

    python3 scripts/excalidraw_import.py my.excalidraw -o my.json [--preset 4:5|3:4|16:9] [--title "..."]
    python3 scripts/render.py --config my.json ...        # then render as usual

What is kept
- rectangles / ellipses / diamonds -> `nodes` (centre, size, rounded corners; fill colour -> nearest Excalidraw hue).
  The text bound inside a shape becomes the node title (first line) and subtitle (the rest).
- arrows / lines -> `edges`. **Bindings are kept**: an arrow whose startBinding/endBinding point at shapes becomes
  `{from, to, fromSide, toSide, fromOff, toOff}` attached to those node ids, so the animation steps can follow it and a
  straight one re-routes when a node moves. Multi-point (elbow / curved) arrows keep their points as `pts` *and* their
  from/to; the view draws `pts` as given, so those do not follow a moved node. Sharp/elbow corners are kept nearly sharp.
  Unbound arrows keep their geometry as `pts`. Dashed / dotted stroke -> `dashed` (dashes march). Text bound to an arrow
  -> its `label`.
- free text -> `texts` (the largest one near the top is treated as the title and gets a highlighter underline).
- frames, images, freedraw and embeddables are skipped (listed on stderr). Shapes are drawn as rounded boxes; rotation
  (`angle`) is ignored. `.excalidrawlib` libraries and clipboard JSON (`excalidraw/clipboard`) import too.

What is generated
- `steps`: the protagonist order. Default: walk the bound arrows from the top-most shape with no incoming arrow
  (breadth first, solid arrows before dashed loop-backs); each step = a node plus one outgoing arrow.
  Override with --order "idA,idB,..." (Excalidraw element ids or node titles). Notes are empty; add `note` per step.
- `period` = 2.5 s per step (rounded to 0.5 s so the boil loops seamlessly).
Coordinates are scaled uniformly into a 1000-wide design space; the view scales that into the canvas.
"""
import argparse, json, math, sys
from collections import deque

HUES = {  # Excalidraw background palette (light) -> live-panel hue names
    "blue": ["#a5d8ff", "#d0ebff", "#74c0fc", "#e7f5ff", "#4dabf7"],
    "green": ["#b2f2bb", "#d3f9d8", "#8ce99a", "#ebfbee", "#69db7c"],
    "red": ["#ffc9c9", "#ffe3e3", "#ffa8a8", "#fff5f5", "#ff8787"],
    "yellow": ["#ffec99", "#fff3bf", "#ffe066", "#fff9db", "#ffd43b"],
    "violet": ["#d0bfff", "#e5dbff", "#b197fc", "#f3f0ff", "#eebefa", "#fcc2d7"],
    "gray": ["#e9ecef", "#dee2e6", "#ced4da", "#f8f9fa"],
}
SHAPES = ("rectangle", "ellipse", "diamond")


def rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def hue_of(bg):
    if not bg or bg == "transparent" or not bg.startswith("#"):
        return "white"
    c = rgb(bg[:7])
    best, bd = "white", 1e9
    for name, cols in HUES.items():
        for col in cols:
            d = sum((a - b) ** 2 for a, b in zip(c, rgb(col)))
            if d < bd:
                best, bd = name, d
    return best if bd < 9000 else "white"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--preset", default="auto", help="auto (16:9 for wide drawings, 1:1 squarish, else 4:5), 4:5, 3:4, 1:1 or 16:9")
    ap.add_argument("--title", default=None)
    ap.add_argument("--order", default=None, help="comma-separated element ids or node titles for the step order")
    ap.add_argument("--step-seconds", type=float, default=2.5)
    a = ap.parse_args()

    doc = json.load(open(a.src, encoding="utf-8"))
    raw = doc.get("elements")
    if raw is None:  # .excalidrawlib: v2 libraryItems[].elements, v1 library[[...]]
        raw = [e for it in doc.get("libraryItems", []) for e in it.get("elements", [])] + \
              [e for it in doc.get("library", []) for e in it]
    els = [e for e in raw if not e.get("isDeleted") and "id" in e and "type" in e]
    for e in els:
        e.setdefault("x", 0); e.setdefault("y", 0); e.setdefault("width", 0); e.setdefault("height", 0)
    by_id = {e["id"]: e for e in els}
    skipped = [e["type"] for e in els if e["type"] in ("frame", "magicframe", "image", "freedraw", "embeddable", "iframe")]
    if skipped:
        print("skipped:", ", ".join(sorted(set(skipped))), file=sys.stderr)

    def pts_abs(e):
        return [[e["x"] + p[0], e["y"] + p[1]] for p in e.get("points", [[0, 0]])]

    # bounding box of everything we draw
    xs, ys = [], []
    for e in els:
        if e["type"] in SHAPES or (e["type"] == "text" and not e.get("containerId")):  # bound text follows its container
            xs += [e["x"], e["x"] + e["width"]]; ys += [e["y"], e["y"] + e["height"]]
        elif e["type"] in ("arrow", "line"):
            for x, y in pts_abs(e):
                xs.append(x); ys.append(y)
    if not xs:
        sys.exit("no drawable elements")
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    M = 60
    s = (1000 - 2 * M) / max(x1 - x0, 1)
    SH = round((y1 - y0) * s + 2 * M + 40)
    X = lambda x: round(M + (x - x0) * s, 1)
    Yc = lambda y: round(M + 20 + (y - y0) * s, 1)
    S = lambda v: round(v * s, 1)

    def text_of(e):
        return (e.get("originalText") or e.get("text") or "").strip()

    # shapes -> nodes
    nodes, nid = [], {}
    for e in els:
        if e["type"] not in SHAPES or e["width"] < 2 or e["height"] < 2:
            continue
        bound = [by_id[b["id"]] for b in (e.get("boundElements") or []) if b.get("type") == "text" and b["id"] in by_id] or \
                [t for t in els if t["type"] == "text" and t.get("containerId") == e["id"]]
        txt = text_of(bound[0]) if bound else ""
        lines = txt.split("\n") if txt else [""]
        w, h = S(e["width"]), S(e["height"])
        n = dict(id=e["id"], t=lines[0], x=X(e["x"] + e["width"] / 2), y=Yc(e["y"] + e["height"] / 2), w=w, h=h,
                 hue=hue_of(e.get("backgroundColor")))
        if len(lines) > 1:
            n["sub"] = "\n".join(lines[1:])
        fs = bound[0].get("fontSize", 20) if bound else 20
        n["size"] = round(max(18, min(56, fs * s * 1.15)))
        if len(lines) > 1:
            n["subSize"] = round(n["size"] * 0.68)
        if e["type"] == "ellipse":
            n["r"] = round(min(w, h) / 2)
        elif e["type"] == "diamond":
            n["r"] = round(min(w, h) / 3)
        elif e.get("roundness"):
            n["r"] = 22
        else:
            n["r"] = 6
        nodes.append(n); nid[e["id"]] = n

    def side_and_off(n, p):
        dx, dy = (p[0] - n["x"]) / max(n["w"] / 2, 1), (p[1] - n["y"]) / max(n["h"] / 2, 1)
        if abs(dx) >= abs(dy):
            return ("right" if dx > 0 else "left"), round(max(-0.9, min(0.9, dy)), 2)
        return ("bottom" if dy > 0 else "top"), round(max(-0.9, min(0.9, dx)), 2)

    def corners(P, c=6):  # the view draws `pts` as a smooth curve: flank each corner so it stays (nearly) sharp
        def toward(v, u):
            L = math.hypot(u[0] - v[0], u[1] - v[1])
            return [round(v[0] + (u[0] - v[0]) * c / L, 1), round(v[1] + (u[1] - v[1]) * c / L, 1)] if L > 3 * c else None
        Q = [P[0]]
        for a0, v, a1 in zip(P, P[1:], P[2:]):
            Q += [q for q in (toward(v, a0), v, toward(v, a1)) if q]
        return Q + [P[-1]]

    # arrows -> edges
    edges, out_of, into = [], {}, {}
    for e in els:
        if e["type"] not in ("arrow", "line"):
            continue
        P = [[X(x), Yc(y)] for x, y in pts_abs(e)]
        if len(P) > 2 and (e.get("elbowed") or not e.get("roundness")):
            P = corners(P)
        sb, eb = (e.get("startBinding") or {}).get("elementId"), (e.get("endBinding") or {}).get("elementId")
        E = {"id": e["id"]}
        if sb in nid and eb in nid:
            A, B = nid[sb], nid[eb]
            E["from"], E["to"] = sb, eb
            E["fromSide"], E["fromOff"] = side_and_off(A, P[0])
            E["toSide"], E["toOff"] = side_and_off(B, P[-1])
            if len(P) > 2:  # elbow / curved: keep the drawn route
                E["pts"] = P
            out_of.setdefault(sb, []).append(E); into.setdefault(eb, []).append(E)
        else:
            E["pts"] = P
            if sb in nid: E["from"] = sb
            if eb in nid: E["to"] = eb
        if e.get("strokeStyle") in ("dashed", "dotted"):
            E["dashed"] = True
        lab = [by_id[b["id"]] for b in (e.get("boundElements") or []) if b.get("type") == "text" and b["id"] in by_id] or \
              [t for t in els if t["type"] == "text" and t.get("containerId") == e["id"]]
        if lab:
            E["label"], E["labelSize"] = text_of(lab[0]), round(max(16, lab[0].get("fontSize", 20) * s))
        edges.append(E)

    def route(E):  # what the view will draw (2-point bound arrows are re-anchored on the node sides)
        if "pts" in E:
            return E["pts"]
        out = []
        for k, sd, off in ((E["from"], E["fromSide"], E["fromOff"]), (E["to"], E["toSide"], E["toOff"])):
            n = nid[k]
            out.append([n["x"] + (n["w"] / 2 if sd == "right" else -n["w"] / 2 if sd == "left" else off * n["w"] / 2),
                        n["y"] + (n["h"] / 2 if sd == "bottom" else -n["h"] / 2 if sd == "top" else off * n["h"] / 2)])
        return out

    def dense(Q, step=8):
        out = []
        for p, q in zip(Q, Q[1:]):
            k = max(1, int(math.hypot(q[0] - p[0], q[1] - p[1]) / step))
            out += [[p[0] + (q[0] - p[0]) * i / k, p[1] + (q[1] - p[1]) * i / k] for i in range(k)]
        return out + [Q[-1]]

    obstacles = [q for E in edges for q in dense(route(E))]
    for E in edges:
        if "label" not in E:
            continue
        Q = route(E)
        seg = [math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(Q, Q[1:])]
        rest, i = sum(seg) / 2, 0
        while i < len(seg) - 1 and rest > seg[i]:
            rest -= seg[i]; i += 1
        L = seg[i] or 1
        dx, dy = Q[i + 1][0] - Q[i][0], Q[i + 1][1] - Q[i][1]
        mid = [Q[i][0] + dx * rest / L, Q[i][1] + dy * rest / L]
        lw, lh = len(max(E["label"].split("\n"), key=len)) * E["labelSize"] * 0.3 + 6, E["labelSize"] * 0.6 + 4  # half extents
        best = None
        for sgn in (-1, 1):  # either side of the arrow, a little further out if it's crowded
            for lift in (1.0, 1.6):
                nx, ny = sgn * -dy / L, sgn * dx / L
                c = [mid[0] + nx * (abs(nx) * lw + abs(ny) * lh + 6) * lift, mid[1] + ny * (abs(nx) * lw + abs(ny) * lh + 6) * lift]
                gap = min([math.hypot(max(abs(q[0] - c[0]) - lw, 0), max(abs(q[1] - c[1]) - lh, 0)) for q in obstacles] +
                          [math.hypot(max(abs(n["x"] - c[0]) - n["w"] / 2 - lw, 0), max(abs(n["y"] - c[1]) - n["h"] / 2 - lh, 0)) for n in nodes])
                score = min(gap, 8) - 6 * (lift - 1) - (0.5 if ny > 0 else 0)  # room first, then close to the line, then above it
                if best is None or score > best[0]:
                    best = (score, c)
        E["labelAt"] = [round(best[1][0], 1), round(best[1][1], 1)]

    # free text -> texts
    texts, free = [], [e for e in els if e["type"] == "text" and not e.get("containerId")]
    title_el = None
    if free:
        top = sorted(free, key=lambda e: (-e.get("fontSize", 20), e["y"]))[0]
        if top["y"] <= y0 + (y1 - y0) * 0.2:
            title_el = top
    for e in free:
        al = e.get("textAlign", "left")
        ax = e["x"] + (e["width"] / 2 if al == "center" else e["width"] if al == "right" else 0)
        T = {"t": text_of(e), "x": X(ax), "y": Yc(e["y"] + e["height"] / 2),
             "size": round(max(14, e.get("fontSize", 20) * s)), "c": "ink", "align": al}
        if e is title_el:
            T["weight"] = 0.6
            T["underline"] = {"hue": "yellow", "width": 16, "dy": round(T["size"] * 0.45), "tilt": -4}
        texts.append(T)

    # steps
    order = []
    if a.order:
        keys = [k.strip() for k in a.order.split(",") if k.strip()]
        title2id = {n["t"]: n["id"] for n in nodes}
        order = [title2id.get(k, k) for k in keys if title2id.get(k, k) in nid]
    else:
        roots = [n for n in nodes if n["id"] in out_of and n["id"] not in into] or \
                [n for n in nodes if n["id"] in out_of]
        seen, q = set(), deque(sorted(roots, key=lambda n: (n["y"], n["x"]))[:1])
        while q:
            n = q.popleft()
            if n["id"] in seen:
                continue
            seen.add(n["id"]); order.append(n["id"])
            for E in sorted(out_of.get(n["id"], []), key=lambda E: (E.get("dashed", False), nid[E["to"]]["y"], nid[E["to"]]["x"])):
                q.append(nid[E["to"]])
        order += [n["id"] for n in sorted(nodes, key=lambda n: (n["y"], n["x"])) if n["id"] not in seen]
    steps, used = [], set()
    for k in order:
        st = {"node": k}
        outs = [E for E in out_of.get(k, []) if E["id"] not in used]
        outs.sort(key=lambda E: E.get("dashed", False))
        if outs:
            st["edge"] = outs[0]["id"]; used.add(outs[0]["id"])
        steps.append(st)
        for E in outs[1:]:  # a fan-out: give each extra arrow its own beat on the same node
            steps.append({"node": k, "edge": E["id"]}); used.add(E["id"])

    period = max(5.0, round(len(steps) * a.step_seconds * 2) / 2)
    view = {"type": "view", "kind": "excalidraw", "space": [1000, SH], "period": period, "t0": 0, "seed": 5,
            "boil": {"step": 0.125, "variants": 4, "amp": 0.5}, "roughness": 1.05, "strokeWidth": 2.6,
            "edgeRough": 0.8, "edgeMulti": False, "noteSize": 28, "edgeGap": 6,
            "texts": texts, "nodes": nodes, "edges": edges, "steps": steps}
    aspect = 1000 / SH
    preset = a.preset
    if preset == "auto":
        preset = "16:9" if aspect > 1.3 else "1:1" if aspect > 0.9 else "4:5"
    canvas = {"preset": preset, "duration": period, "fps": 30}
    if preset == "16:9":
        canvas.update(width=1920, height=1080)
    cfg = {
        "meta": {"title": a.title or (text_of(title_el) if title_el else "excalidraw import"), "source": a.src},
        "canvas": canvas,
        "theme": {"preset": "light-pastel", "font": 'Excalifont, Xiaolai, "Noto Sans CJK SC", sans-serif',
                  "fonts": [{"family": "Excalifont", "src": "Excalifont-Regular-Latin.woff2", "weight": "400"},
                            {"family": "Xiaolai", "src": "Xiaolai-Regular.ttf", "weight": "400"}],
                  "colors": {"bg": "#ffffff"}},
        "elements": [view],
    }
    json.dump(cfg, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    nb = sum(1 for E in edges if "from" in E and "to" in E)
    print(f"wrote {a.out}: {len(nodes)} nodes, {len(edges)} edges ({nb} bound), {len(texts)} texts, {len(steps)} steps, period {period}s, canvas {preset}")


if __name__ == "__main__":
    main()
