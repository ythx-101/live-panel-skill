---
name: live-panel
description: Build a terminal-style, always-running animated architecture diagram (a "live panel") from a JSON config and render it to an mp4. Use when the user wants a system, agent or org architecture diagram that looks like a monitoring dashboard in a terminal window - fixed layout, glowing packets on the wires, scrolling log, counters, bars that flip state - as a screen-recording-style video or a live web page, instead of a static picture or a step-by-step reveal. 中文：当用户要做"活的"架构图、agent 树或系统监控面板风格的动画（mp4 视频或循环网页）时使用——终端里一直在跑的监控面板外观，固定布局、线上流动的数据包、滚动日志、翻转的计数器和状态条；不是静态图，也不是分步演示。
---

# live-panel

Turn a description of a system into an **always-running architecture diagram**: one fixed page that looks like a monitoring panel of a running system. Every frame is a complete, readable diagram; what moves is system state, not decoration. Two built-in themes: `terminal-dark` (the original look) and `light-pastel` (white background, rounded pastel boxes - for infographics, e.g. Xiaohongshu). Canvas presets: `4:5` (X, 1200x1500), `3:4` (Xiaohongshu, 1080x1440), `1:1` (1080x1080). Intended as the base for posts on X and Xiaohongshu.

> **Credit.** The look and the motion idea come from an architecture-diagram clip by **@thedelost** (a Codex agent-tree panel, generated with GPT and screen-recorded as a web page): https://x.com/thedelost/status/2105398038026195279 . It reached many people through a quote-post by **@slashui**: https://x.com/slashui/status/2105850132365443528 . This skill is an independent re-implementation of the *method* (the motion grammar was learned by analysing that clip). `examples/codex-agents/` is a recreation of the original picture and stays the original author's design. Keep this credit when you publish output made with the skill's Codex example.

## When to use

- The user asks for an architecture / agent-tree / org-chart / data-flow diagram that should feel alive (video, GIF-like loop, or live page).
- The user has a description of a system with a few boxes, a flow between them, a few "on call" side triggers, a log and some numbers.
- Not for: diagrams that need interaction, real telemetry, or step-by-step explanations (use a slide or a normal diagram tool).

## Input

A single JSON config (schema: `references/config-schema.md`). It holds everything: canvas size, colours, boxes with lines of text, wires, packet paths, side-rail triggers, log wording, numbers. **The template never needs editing.** Start from the closest example: `examples/codex-agents/config.json` (terminal-dark, 4:5, recreation of @thedelost's picture), `examples/airbnb/config.json` (terminal-dark, Chinese content, figures from an interview) or `examples/agent-architecture/config.json` (light-pastel, 3:4, a static Xiaohongshu infographic made to move, original by 小红书 @林纾). Theme: `theme.preset`; canvas: `canvas.preset`. Positions are absolute canvas pixels, so another aspect ratio needs its own config.

## Choosing a view (视图)

If the content has one clear shape, use a `{"type":"view"}` element instead of placing boxes by hand (contract: `references/views.md`; gate: `scripts/verify_view.py` must PASS all 7 combos):
- repeating loop → `ring`; stage-by-stage drop-off → `funnel` (both ready, see `examples/ring/`, `examples/funnel/`).
- nested workflow with decisions and loop-backs (retry on "no", outer/inner loop, human gate) → `loop` (ready, see `examples/loop-poteto/`).
- relationships/clusters → `nebula`; work over time/parallel tracks → `timeline`; hierarchy → `tree`; a few watched numbers → `kpi` (planned, not in this version yet).
- a hand-drawn Excalidraw-style diagram (pastel boxes, handwritten text, loops) that should keep moving → `excalidraw` (ready, see `examples/excalidraw-aqua/`, `examples/excalidraw-gardener/`; run `scripts/fetch_fonts.sh` once for the CJK hand font). The user already has a `.excalidraw` file → `python3 scripts/excalidraw_import.py file.excalidraw -o config.json` first (keeps arrow bindings, writes nodes/edges/steps), then add notes and render.
- an architecture with arbitrary boxes and wires → no view, free-form elements as in the original examples.

## Fixed procedure

1. **Collect content and where each number comes from.** List boxes, who talks to whom, which things are "on call" triggers, what the log would say. Write the source (link or "simulated") next to every number. If a number has no real source, it is simulated: say so on screen (a footer line, or "(illustrative)" next to the counter). Never invent a figure and present it as real.
2. **Write the config - scaffold first, then iterate.** For boxes in rows (an agent tree, a pipeline, a fan-out/merge, a monitoring panel, with or without a side rail of on-call triggers), write a short spec - what each box says, rows top to bottom, optional `lane` (running/done), `gauge` (bar that flips past a threshold), `rail`, `counters`, `log`, `note`, `credit`; `python3 scripts/scaffold.py --example` prints one - and run `python3 scripts/scaffold.py --spec spec.json --out out/config.json`. It does the pixel layout, wires, packets, rail arrows, log columns and text wrapping, and its output usually passes `check_frames.py` on the first run; then edit the output (or the spec) in small steps. For a layout it cannot express (a centre box with satellites, curved arrows, a recreated picture with its own geometry), copy the closest example to your output path with a shell command (`cp examples/<closest>/config.json out/config.json`), or write a short Python script that builds the dict and dumps the JSON; then change it in small edits. Never type a whole config into a single message or tool call: a 20-40 KB JSON in one write is the most common way an agent run dies before anything is saved. Have a runnable draft on disk by your fifth tool call at the latest, then work in a loop: change one to three boxes, run `check_frames.py`, read its `PROBLEM` lines, fix, repeat. Do not plan coordinates or count text widths in your reasoning: if you catch yourself doing pixel arithmetic for more than a few lines, stop and write the edit instead - long in-head layout planning is the other way runs die before saving anything. Place boxes on a pixel grid (x, y, w, h in canvas px); text lines flow inside boxes at one fixed line height. Put the credit/source line in the top-level `credit` key (`"credit": {"text": "...", "y": ...}`); a plain text element at the bottom is not read as the credit. Skim `references/motion-grammar.md` before choosing machines and periods; `references/config-schema.md` lists every key, so you rarely need to read `assets/template.html`.
3. **Render.** `python3 scripts/render.py --config my.json --out my.mp4` (needs Chrome/Chromium and ffmpeg on PATH, or `--chrome` / `--ffmpeg`; on macOS the browser is also found under `/Applications/*.app`). Linux and macOS only - on Windows run the scripts inside WSL. `--html-out page.html` also keeps the self-contained page, which runs live in any browser.
4. **Check by frames, not by trust.** `python3 scripts/check_frames.py --config my.json --out-dir frames --repeat` samples ~120 time points, measures text overflow and overlaps from the DOM, exports PNGs and proves replay determinism. Open the PNGs and look: the checker catches geometry, not taste. Fix the config and repeat until it exits 0. For `text overflows its box`, take the cheapest fix - shorten the text, drop a size step, or widen that one box - rather than redesigning the layout; a config that passes beats a better one that is still being planned when time runs out.

## Motion rules in one screen

(Full text and rationale: `references/motion-grammar.md`.)

- **Layout never moves.** No camera, no step-by-step reveal. Frame 0 is already a complete diagram.
- **Three tempos at once**: fast (packets with trails on every wire, spinners, fast counters), medium (log scrolls with newest line bright and older grey; bars re-roll and flip colour and label past a threshold), slow (side-rail triggers light up one at a time in order, their arrow changes colour and carries a packet, advice is typed out, totals accumulate).
- **One truth everywhere.** The number in the log is the number on the bar; the trigger lit in the rail is the one the log mentions; counters in the status bar equal counters in boxes. In this engine that holds by construction: log lines are generated from the same state machines as the boxes.
- **No real data? Say "illustrative".** Fixed facts stay fixed; only the animation's own counters move, and they are labelled.

## Determinism (why it renders the same every time)

The page exposes `window.seek(t)`. Every visual is a pure function of `t` (and a fixed integer seed for the few "random" picks): no wall clock, no `Math.random`, no CSS animation. The renderer calls `seek(i/fps)` and screenshots; `check_frames.py --repeat` seeks away and back and compares bytes. Opened in a normal browser (no `?manual`), the same function is driven by `requestAnimationFrame` and loops.

## Files

- `assets/template.html` - the generic page. `scripts/scaffold.py` - short spec -> complete config (layout done for you). `scripts/render.py` - mp4. `scripts/check_frames.py` - checks + PNGs. `scripts/livepanel.py` - shared helpers (Chrome over the DevTools pipe, stdlib only).
- `references/motion-grammar.md`, `references/config-schema.md`.
- `examples/codex-agents/`, `examples/airbnb/`, `examples/agent-architecture/` - config, mp4 and an animated `preview.webp`. `examples/ring/`, `examples/funnel/`, `examples/funnel-karpathy/` (log scale, mono palette), `examples/loop-poteto/` (grouped loop with decisions) - view examples.
- `assets/views/<kind>.js` - one file per view; `references/views.md`, `references/view-rules.md`, `references/verify-view.md`; `scripts/verify_view.py`.

## Light theme notes

For infographics keep the original colours and structure; motion is gentler: small packets drift along every arrow, state-bound arrows turn the accent colour and carry two packets, active boxes get a glow, lists (steps, tools) light one row at a time from one shared `cycle` machine so that everything on screen refers to the same step. Use `container:true` on boxes that hold other boxes so the checker does not call nested boxes overlapping, and `inside:true` on icon text placed on a box.

## Credit rule

Always put the original author and link of any picture you re-animate or recreate in the video footer (`credit`) and in the post: the author's handle **and the full URL exactly as the user gave it** (e.g. `原图：小红书 @作者《标题》 https://... · 动态复刻，非原作者作品`). A handle without the link, or a link without the handle, is not enough. When the user gives a source for a real figure (a report, an interview), name that source in `credit` too. State when a figure is simulated.
