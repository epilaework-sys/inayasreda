#!/usr/bin/env python3
"""PPTX презентации членства: один HTML-слайд = один PPTX-слайд.

Шаг 0 — базовая картинка. Шаги 1…N — полноэкранные кадры с Appear on click.
По умолчанию — светлая тема (?light). Флаг --dark для тёмной.
"""

from __future__ import annotations

import http.server
import os
import re
import shutil
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

from pptx import Presentation
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Emu, Inches

ROOT = Path(__file__).resolve().parents[1]
DECK = ROOT / "deck"
HTML = DECK / "membership.html"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
W, H = 1920, 1080
SLIDE_W = Inches(13.333333)
SLIDE_H = Inches(7.5)

LIGHT = "--dark" not in sys.argv
SHOTS = Path("/tmp/pptx-membership-shots-light" if LIGHT else "/tmp/pptx-membership-shots-dark")
OUT = ROOT / ("inaya-sreda-membership-light.pptx" if LIGHT else "inaya-sreda-membership.pptx")
BG = (242, 239, 233) if LIGHT else (31, 30, 28)
THEME_QS = "light" if LIGHT else "dark"


def count_steps(html: str) -> list[int]:
    stages = re.findall(r'<section class="stage[^"]*"[^>]*>(.*?)</section>', html, re.S)
    out = []
    for body in stages:
        nums = [int(n) for n in re.findall(r'data-step="(\d+)"', body)]
        out.append(max(nums) if nums else 0)
    return out


def start_server(port: int = 8796):
    os.chdir(DECK)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def copyfile(self, source, outputfile):
            try:
                super().copyfile(source, outputfile)
            except (BrokenPipeError, ConnectionResetError):
                pass

    class ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    httpd = ThreadingServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, port


def screenshot(url: str, dest: Path):
    shot_path = Path("/tmp") / f"pptx-mcap-{dest.stem}.png"
    udir = f"/tmp/chrome-pptx-m-{dest.stem}"
    shot_path.unlink(missing_ok=True)
    shutil.rmtree(udir, ignore_errors=True)
    cmd = [
        CHROME,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        f"--window-size={W},{H}",
        f"--screenshot={shot_path}",
        "--virtual-time-budget=5000",
        "--run-all-compositor-stages-before-draw",
        "--no-first-run",
        "--disable-background-networking",
        f"--user-data-dir={udir}",
        url,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 35
    try:
        while time.time() < deadline:
            if shot_path.exists() and shot_path.stat().st_size > 800:
                time.sleep(0.6)
                break
            if proc.poll() is not None:
                break
            time.sleep(0.25)
    finally:
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
        shutil.rmtree(udir, ignore_errors=True)
        subprocess.run(
            ["pkill", "-f", f"user-data-dir={udir}"],
            capture_output=True,
        )

    if not shot_path.exists() or shot_path.stat().st_size < 800:
        raise RuntimeError(f"chrome screenshot missing/empty: {url}")

    from PIL import Image

    im = Image.open(shot_path).convert("RGB")
    shot_path.unlink(missing_ok=True)
    if im.size != (W, H):
        im = im.crop((0, 0, min(W, im.size[0]), min(H, im.size[1])))
        if im.size != (W, H):
            canvas = Image.new("RGB", (W, H), BG)
            canvas.paste(im, (0, 0))
            im = canvas
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "JPEG", quality=88, optimize=True)


def capture_all(step_counts: list[int], port: int):
    SHOTS.mkdir(parents=True, exist_ok=True)
    total = sum(c + 1 for c in step_counts)
    n = 0
    for si, steps in enumerate(step_counts, start=1):
        for k in range(steps + 1):
            n += 1
            dest = SHOTS / f"s{si:02d}-k{k:02d}.jpg"
            if dest.exists() and dest.stat().st_size > 800:
                print(f"[{n}/{total}] slide {si} step {k} skip", flush=True)
                continue
            url = f"http://127.0.0.1:{port}/membership.html?{THEME_QS}&k={k}#{si}"
            print(f"[{n}/{total}] slide {si} step {k}", flush=True)
            last_err = None
            for attempt in range(1, 4):
                try:
                    screenshot(url, dest)
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    print(f"  retry {attempt}/3: {e}", flush=True)
                    time.sleep(1)
            if last_err:
                raise last_err


def fix_sldsz_type(path: Path):
    import zipfile

    tmp = path.with_suffix(".pptx.tmp")
    with zipfile.ZipFile(path, "r") as zin, zipfile.ZipFile(tmp, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "ppt/presentation.xml":
                text = data.decode("utf-8")
                text = text.replace('type="screen4x3"', 'type="screen16x9"')
                data = text.encode("utf-8")
            zout.writestr(item, data)
    tmp.replace(path)


def apply_powerpoint_animations(path: Path):
    script = f'''
tell application "Microsoft PowerPoint"
    activate
    try
        close every presentation saving no
    end try
    delay 0.5
    open POSIX file "{path}"
    delay 2
    set pres to active presentation
    set slideCount to count of slides of pres
    repeat with s from 1 to slideCount
        set sl to slide s of pres
        set seq to main sequence of timeline of sl
        set n to count of shapes of sl
        if n > 1 then
            repeat with i from 2 to n
                try
                    add effect seq for shape i of sl fx animation type appear trigger on page click
                end try
            end repeat
        end if
    end repeat
    save pres
    close pres saving yes
end tell
'''
    print("applying Appear via PowerPoint…", flush=True)
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        print("PowerPoint AppleScript skipped:\n", r.stderr or r.stdout, flush=True)
        return False
    print("PowerPoint saved animations", flush=True)
    return True


def blank_layout(prs: Presentation):
    for layout in prs.slide_layouts:
        if layout.name.lower() in ("blank", "пустой слайд", "пустой"):
            return layout
    return prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[-1]


def build_pptx(step_counts: list[int]):
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    layout = blank_layout(prs)

    for si, steps in enumerate(step_counts, start=1):
        slide = prs.slides.add_slide(layout)
        for shape in list(slide.shapes):
            sp = shape._element
            sp.getparent().remove(sp)

        base = SHOTS / f"s{si:02d}-k00.jpg"
        if not base.exists():
            raise SystemExit(f"missing shot {base}")

        slide.shapes.add_picture(str(base), Emu(0), Emu(0), SLIDE_W, SLIDE_H)
        extras = 0
        for k in range(1, steps + 1):
            path = SHOTS / f"s{si:02d}-k{k:02d}.jpg"
            if not path.exists():
                raise SystemExit(f"missing shot {path}")
            slide.shapes.add_picture(str(path), Emu(0), Emu(0), SLIDE_W, SLIDE_H)
            extras += 1

        print(f"  slide {si}: base + {extras} overlay(s)", flush=True)

    prs.save(str(OUT))
    fix_sldsz_type(OUT)
    print(f"saved {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)", flush=True)
    apply_powerpoint_animations(OUT)


def main():
    if not Path(CHROME).exists():
        sys.exit("Chrome not found")
    if not HTML.exists():
        sys.exit(f"missing {HTML}")
    html = HTML.read_text(encoding="utf-8")
    step_counts = count_steps(html)
    print(f"theme={'light' if LIGHT else 'dark'} → {OUT.name}", flush=True)
    print(f"{len(step_counts)} slides, steps={step_counts}", flush=True)

    if "--fresh" in sys.argv:
        shutil.rmtree(SHOTS, ignore_errors=True)

    if "--pptx-only" in sys.argv:
        build_pptx(step_counts)
        return
    httpd, port = start_server()
    time.sleep(0.3)
    try:
        capture_all(step_counts, port)
        build_pptx(step_counts)
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    main()
