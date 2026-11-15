#!/usr/bin/env python3
"""Светлый PPTX зала: один слайд HTML = один слайд PPTX.

Шаг 0 — базовая картинка. Шаги 1…N — полноэкранные кадры с Appear on click.
Видео не вшивается — слоты 7 / 25 / 26 остаются кадрами-постерами;
ролики можно вставить в PowerPoint вручную поверх.
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
# Путь без пробелов: headless Chrome на macOS зависает, если --screenshot
# указывает в каталог с пробелом в имени.
SHOTS = Path("/tmp/pptx-light-shots")
OUT = ROOT / "inaya-sreda-2-goda-light.pptx"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
W, H = 1920, 1080
# Стандартный widescreen 16:9. Нестандартный размер + type=screen4x3
# ломает файл — PowerPoint предлагает «Восстановить» и выкидывает анимации.
SLIDE_W = Inches(13.333333)
SLIDE_H = Inches(7.5)



def count_steps(html: str) -> list[int]:
    """Max data-step per stage (0 if none)."""
    stages = re.findall(r'<section class="stage[^"]*"[^>]*>(.*?)</section>', html, re.S)
    out = []
    for body in stages:
        nums = [int(n) for n in re.findall(r'data-step="(\d+)"', body)]
        out.append(max(nums) if nums else 0)
    return out


def start_server(port: int = 8795):
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


def screenshot(url: str, dest: Path, port: int):
    """Снять кадр. Chrome часто пишет файл и не выходит — убиваем процесс после файла."""
    shot_path = Path("/tmp") / f"pptx-cap-{dest.stem}.png"
    udir = f"/tmp/chrome-pptx-{dest.stem}"
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
                time.sleep(0.6)  # дописать файл
                break
            if proc.poll() is not None:
                break
            time.sleep(0.25)
        else:
            pass
    finally:
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
        shutil.rmtree(udir, ignore_errors=True)
        # stray chrome helpers for this profile
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
            canvas = Image.new("RGB", (W, H), (242, 239, 233))
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
            url = f"http://127.0.0.1:{port}/index.html?light&k={k}#{si}"
            print(f"[{n}/{total}] slide {si} step {k}", flush=True)
            last_err = None
            for attempt in range(1, 4):
                try:
                    screenshot(url, dest, port)
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    print(f"  retry {attempt}/3: {e}", flush=True)
                    time.sleep(1)
            if last_err:
                raise last_err


def _sub(parent, tag, **attrs):
    el = OxmlElement(tag)
    for k, v in attrs.items():
        el.set(k, str(v))
    parent.append(el)
    return el


def set_timing(slide, appear_spids: list[int], video_spid: int | None = None):
    """Appear on click: PowerPoint ждёт клик только если у группы delay=indefinite."""
    sld = slide._element
    for t in sld.xpath("./p:timing"):
        sld.remove(t)
    if not appear_spids:
        return

    nid = 3
    groups = []
    for spid in appear_spids:
        a, b, c, d = nid, nid + 1, nid + 2, nid + 3
        nid += 4
        groups.append(
            f'<p:par><p:cTn id="{a}" fill="hold">'
            f'<p:stCondLst><p:cond delay="indefinite"/></p:stCondLst>'
            f'<p:childTnLst><p:par><p:cTn id="{b}" fill="hold">'
            f'<p:stCondLst><p:cond delay="0"/></p:stCondLst>'
            f'<p:childTnLst><p:par>'
            f'<p:cTn id="{c}" presetID="1" presetClass="entr" presetSubtype="0" '
            f'fill="hold" grpId="0" nodeType="clickEffect">'
            f'<p:stCondLst><p:cond delay="0"/></p:stCondLst>'
            f'<p:childTnLst><p:set><p:cBhvr>'
            f'<p:cTn id="{d}" dur="1" fill="hold">'
            f'<p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
            f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'
            f'<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>'
            f'</p:cBhvr><p:to><p:strVal val="visible"/></p:to>'
            f'</p:set></p:childTnLst></p:cTn></p:par></p:childTnLst>'
            f'</p:cTn></p:par></p:childTnLst></p:cTn></p:par>'
        )
    bld = "".join(f'<p:bldP spid="{s}" grpId="0" animBg="1"/>' for s in appear_spids)
    xml = (
        f'<p:timing {nsdecls("p")}>'
        f'<p:tnLst><p:par>'
        f'<p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">'
        f'<p:childTnLst>'
        f'<p:seq concurrent="enabled" nextAc="seek">'
        f'<p:cTn id="2" dur="indefinite" nodeType="mainSeq">'
        f'<p:childTnLst>{"".join(groups)}</p:childTnLst>'
        f'</p:cTn>'
        f'<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
        f'<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst>'
        f'</p:seq></p:childTnLst></p:cTn></p:par></p:tnLst>'
        f'<p:bldLst>{bld}</p:bldLst></p:timing>'
    )
    sld.append(parse_xml(xml))


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
    """Appear on click пишет сам PowerPoint — его XML приложение не отвергает."""
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
        print("PowerPoint AppleScript failed:\n", r.stderr or r.stdout, flush=True)
        raise SystemExit(1)
    print("PowerPoint saved animations", flush=True)


def blank_layout(prs: Presentation):
    # Use blank layout from first available
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
    # type=screen4x3 при 16:9 размерах — частая причина «восстановить»
    fix_sldsz_type(OUT)
    print(f"saved {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)", flush=True)
    apply_powerpoint_animations(OUT)


def main():
    if not Path(CHROME).exists():
        sys.exit("Chrome not found")
    html = (DECK / "index.html").read_text(encoding="utf-8")
    step_counts = count_steps(html)
    print(f"{len(step_counts)} slides, steps={step_counts}", flush=True)

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
