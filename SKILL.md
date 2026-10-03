---
name: live-panel
description: Use when 要做活的架构图/agent树/系统监控面板风格的动画图（视频/循环页），从 JSON config 渲染成 mp4。终端的 always-running 监控面板外观：固定布局、线上流动的数据包、滚动日志、翻转的计数器和状态条，可做 X/小红书配图。不用静态图或分步演示。
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

## Fixed procedure

1. **Collect content and where each number comes from.** List boxes, who talks to whom, which things are "on call" triggers, what the log would say. Write the source (link or "simulated") next to every number. If a number has no real source, it is simulated: say so on screen (a footer line, or "(illustrative)" next to the counter). Never invent a figure and present it as real.
2. **Write the config.** Copy an example. Place boxes on a pixel grid (x, y, w, h in canvas px); text lines flow inside boxes at one fixed line height. Put the credit/source line in `credit`. Read `references/motion-grammar.md` before choosing machines and periods.
3. **Render.** `python3 scripts/render.py --config my.json --out my.mp4` (needs Chrome/Chromium and ffmpeg on PATH, or `--chrome` / `--ffmpeg`). `--html-out page.html` also keeps the self-contained page, which runs live in any browser. **On macOS the browser is auto-detected from `/Applications/*.app`** (Homebrew's `chromium` shim on PATH often launches then dies with `Chrome closed the pipe`); pass `--chrome` to override.
4. **Check by frames, not by trust.** `python3 scripts/check_frames.py --config my.json --out-dir frames --repeat` samples ~120 time points, measures text overflow and overlaps from the DOM, exports PNGs and proves replay determinism. Open the PNGs and look: the checker catches geometry, not taste. Fix the config and repeat until it exits 0.

## Motion rules in one screen

(Full text and rationale: `references/motion-grammar.md`.)

- **Layout never moves.** No camera, no step-by-step reveal. Frame 0 is already a complete diagram.
- **Three tempos at once**: fast (packets with trails on every wire, spinners, fast counters), medium (log scrolls with newest line bright and older grey; bars re-roll and flip colour and label past a threshold), slow (side-rail triggers light up one at a time in order, their arrow changes colour and carries a packet, advice is typed out, totals accumulate).
- **One truth everywhere.** The number in the log is the number on the bar; the trigger lit in the rail is the one the log mentions; counters in the status bar equal counters in boxes. In this engine that holds by construction: log lines are generated from the same state machines as the boxes.
- **No real data? Say "illustrative".** Fixed facts stay fixed; only the animation's own counters move, and they are labelled.

## Determinism (why it renders the same every time)

The page exposes `window.seek(t)`. Every visual is a pure function of `t` (and a fixed integer seed for the few "random" picks): no wall clock, no `Math.random`, no CSS animation. The renderer calls `seek(i/fps)` and screenshots; `check_frames.py --repeat` seeks away and back and compares bytes. Opened in a normal browser (no `?manual`), the same function is driven by `requestAnimationFrame` and loops.

## Files

- `assets/template.html` - the generic page. `scripts/render.py` - mp4. `scripts/check_frames.py` - checks + PNGs. `scripts/livepanel.py` - shared helpers (Chrome over the DevTools pipe, stdlib only).
- `references/motion-grammar.md`, `references/config-schema.md`.
- `examples/codex-agents/`, `examples/airbnb/`, `examples/agent-architecture/` - config, mp4 and screenshots.

## Light theme notes

For infographics keep the original colours and structure; motion is gentler: small packets drift along every arrow, state-bound arrows turn the accent colour and carry two packets, active boxes get a glow, lists (steps, tools) light one row at a time from one shared `cycle` machine so that everything on screen refers to the same step. Use `container:true` on boxes that hold other boxes so the checker does not call nested boxes overlapping, and `inside:true` on icon text placed on a box.

## Credit rule

Always put the original author and link of any picture you re-animate or recreate in the video footer (`credit`) and in the post. State when a figure is simulated.
