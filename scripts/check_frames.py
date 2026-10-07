#!/usr/bin/env python3
"""Sample frames of a live-panel config, check text overflow / overlap by DOM measurement, export a few PNGs,
and (with --repeat) prove replays are identical.

  python3 scripts/check_frames.py --config examples/airbnb/config.json --out-dir /tmp/check
Exit status 1 when any problem is found. With --video, the PNGs are cut from that mp4 instead of the live page.
"""
import argparse, base64, os, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import livepanel as lp


TOL_PIXELS = 50   # allowed number of visibly different pixels (sub-pixel anti-aliasing noise); a real state difference changes thousands


def pixel_diff(br, a, b, delta=24):
    """Compare two PNGs inside the browser: count of pixels differing by more than `delta` in any channel, and the max delta.
    (Anti-aliasing at a sub-pixel edge can differ by a few levels between repaints; a real state difference is far larger.)"""
    ja = base64.b64encode(a).decode(); jb = base64.b64encode(b).decode()
    js = '''(async()=>{const L=s=>new Promise(r=>{const i=new Image();i.onload=()=>r(i);i.src='data:image/png;base64,'+s});
      const A=await L(%r),B=await L(%r),c=document.createElement('canvas');c.width=A.width;c.height=A.height;const x=c.getContext('2d');
      x.drawImage(A,0,0);const da=x.getImageData(0,0,c.width,c.height).data;x.clearRect(0,0,c.width,c.height);x.drawImage(B,0,0);const db=x.getImageData(0,0,c.width,c.height).data;
      let n=0,m=0;for(let i=0;i<da.length;i+=4){const d=Math.max(Math.abs(da[i]-db[i]),Math.abs(da[i+1]-db[i+1]),Math.abs(da[i+2]-db[i+2]));if(d>m)m=d;if(d>%d)n++}return [n,m]})()''' % (ja, jb, delta)
    return br.eval(js)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out-dir", required=True, help="where the PNGs go")
    ap.add_argument("--samples", type=int, default=120, help="how many time points to measure (DOM only, cheap)")
    ap.add_argument("--png", type=int, default=4, help="how many PNGs to export")
    ap.add_argument("--video", help="cut the PNGs from this mp4 instead of the page")
    ap.add_argument("--repeat", action="store_true", help="screenshot each exported time twice (with a seek elsewhere in between) and compare the pixels")
    ap.add_argument("--chrome"); ap.add_argument("--ffmpeg"); ap.add_argument("--template")
    ap.add_argument("--no-sandbox", action="store_true")
    a = ap.parse_args()
    chrome = lp.find_chrome(a.chrome)
    os.makedirs(a.out_dir, exist_ok=True)
    page = os.path.join(tempfile.mkdtemp(prefix="livepanel-page-"), "page.html")
    cfg = lp.build_page(a.config, page, a.template)
    w, h, dur, _ = lp.canvas(cfg)
    times = [dur * i / a.samples + 0.013 * i for i in range(a.samples)]
    shots = [dur * (i + 0.5) / a.png for i in range(a.png)]
    problems = {}
    with lp.Chrome(chrome, w, h, True if a.no_sandbox else None) as br:
        br.open("file://" + os.path.abspath(page) + "?manual")
        for t in times + shots:
            br.seek(t)
            for p in br.eval("window.__check()"):
                problems.setdefault(p, []).append(round(t, 2))
        err = br.eval("window.__error||''")
        if err:
            problems["page error: " + err] = [0]
        same = True
        for i, t in enumerate(shots):
            name = Path(a.out_dir) / f"frame_{i + 1}_t{t:05.2f}.png"
            br.seek(t); png = br.shot()
            if not a.video:
                name.write_bytes(png)
            if a.repeat:
                br.seek((t + dur / 2) % dur); br.shot()
                br.seek(t); again = br.shot()
                n, mx = pixel_diff(br, png, again)
                ok = n <= TOL_PIXELS
                same &= ok
                print(f"replay t={t:.2f}s: {n} pixels differ visibly (max channel delta {mx}) -> {'identical' if ok else 'DIFFERENT'}")
    if a.video:
        ffmpeg = lp.find_exe(a.ffmpeg, ["ffmpeg"], "ffmpeg")
        for i, t in enumerate(shots):
            subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", a.video, "-frames:v", "1",
                            str(Path(a.out_dir) / f"frame_{i + 1}_t{t:05.2f}.png")], check=True)
    for p, ts in problems.items():
        print(f"PROBLEM: {p}  (first at t={ts[0]}s, {len(ts)} of {a.samples + a.png} samples)")
    print(f"checked {a.samples + a.png} time points, {len(problems)} distinct problems; PNGs in {a.out_dir}")
    if a.repeat and not same:
        sys.exit(1)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
