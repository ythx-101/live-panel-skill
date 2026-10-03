#!/usr/bin/env python3
"""Render a live-panel config to an H.264 mp4: step window.seek(t) frame by frame, screenshot, pipe into ffmpeg.

  python3 scripts/render.py --config examples/codex-agents/config.json --out out.mp4
Chrome and ffmpeg are looked up on PATH unless --chrome / --ffmpeg are given.
"""
import argparse, os, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import livepanel as lp


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True, help="path to the JSON config")
    ap.add_argument("--out", required=True, help="output .mp4")
    ap.add_argument("--width", type=int, help="video width (default: config canvas.width)")
    ap.add_argument("--height", type=int, help="video height (default: config canvas.height)")
    ap.add_argument("--duration", type=float, help="seconds (default: config canvas.duration)")
    ap.add_argument("--fps", type=int, help="frames per second (default: config canvas.fps or 30)")
    ap.add_argument("--chrome", help="Chrome/Chromium executable (default: search PATH)")
    ap.add_argument("--ffmpeg", help="ffmpeg executable (default: search PATH)")
    ap.add_argument("--template", help="alternative template.html")
    ap.add_argument("--crf", type=int, default=16)
    ap.add_argument("--audio", choices=["silent", "none"], default="silent", help="add a silent AAC track (some chat apps treat silent-less mp4 as a GIF)")
    ap.add_argument("--html-out", help="also keep the generated self-contained page here (opens live in any browser)")
    ap.add_argument("--keep-frames", help="also write PNG frames into this directory")
    ap.add_argument("--no-sandbox", action="store_true", help="pass --no-sandbox to Chrome (auto when running as root)")
    a = ap.parse_args()

    chrome = lp.find_chrome(a.chrome)
    ffmpeg = lp.find_exe(a.ffmpeg, ["ffmpeg"], "ffmpeg")
    tmpdir = tempfile.mkdtemp(prefix="livepanel-page-")
    page = a.html_out or os.path.join(tmpdir, "page.html")
    cfg = lp.build_page(a.config, page, a.template)
    cw, ch, cdur, cfps = lp.canvas(cfg)
    w = a.width or cw; h = a.height or ch
    fps = a.fps or cfps; dur = a.duration or cdur
    n = int(round(fps * dur))
    w -= w % 2; h -= h % 2   # yuv420p needs even sizes
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png", "-i", "-"]
    if a.audio == "silent":
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-shortest", "-c:a", "aac", "-b:a", "32k"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", str(a.crf), "-pix_fmt", "yuv420p", "-r", str(fps), "-movflags", "+faststart", a.out]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    if a.keep_frames:
        os.makedirs(a.keep_frames, exist_ok=True)
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with lp.Chrome(chrome, w, h, True if a.no_sandbox else None) as br:
        br.open("file://" + os.path.abspath(page) + "?manual")
        for i in range(n):
            br.seek(i / fps)
            png = br.shot()
            if a.keep_frames:
                Path(a.keep_frames, f"f_{i:04d}.png").write_bytes(png)
            ff.stdin.write(png)
            if i % fps == 0:
                print(f"\r{i}/{n} frames", end="", file=sys.stderr, flush=True)
        err = br.eval("window.__error||''")
        if err:
            print("\npage errors:", err, file=sys.stderr)
    ff.stdin.close(); rc = ff.wait()
    print(f"\nwrote {a.out} ({n} frames, {w}x{h}@{fps})", file=sys.stderr)
    sys.exit(rc)


if __name__ == "__main__":
    main()
