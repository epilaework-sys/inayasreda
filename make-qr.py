"""Генератор QR-кодов для дека.

Светлая плашка с тёмными модулями, а не наоборот: инвертированные QR
читают не все сканеры, а на юбилее переспросить будет не у кого.
Цвета — из палитры бренда, в центре звезда из логотипа.

Коррекция ошибок H (30%) — запас на звезду в центре и на то,
что снимать будут с рук из зала.

Запуск:
    python3 make-qr.py https://inayasreda.ru/ deck/qr-site.png
    python3 make-qr.py https://inayasreda.ru/ deck/qr-site-light.png paper

Третий аргумент — поле кода. `deck` (по умолчанию) даёт #D8E0E0 под тёмный
дек, `paper` — #F2EFE9 под светлую тему: иначе плашка читается на бумаге
как холодная серая заплата.
"""

import sys

import segno
from PIL import Image

FIELDS = {
    "deck": "#d8e0e0",     # светлый из палитры логотипа
    "paper": "#f2efe9",    # фон светлой темы
}
SCALE = 32
MARK = "brand/logo-mark.png"


def make(url, out, field="deck", with_mark=True):
    light = FIELDS[field]
    qr = segno.make(url, error="h")
    qr.save("/tmp/_qr.png", scale=SCALE, border=4, dark="#141413", light=light)
    im = Image.open("/tmp/_qr.png").convert("RGB")
    w, h = im.size

    if with_mark:
        # Звезда занимает ~17% ширины — H-коррекция такое перекрытие держит.
        star = Image.open(MARK).convert("RGBA")
        side = int(w * 0.17)
        star = star.resize((side, side), Image.LANCZOS)

        pad = int(side * 0.28)
        plate = Image.new("RGB", (side + pad * 2, side + pad * 2), light)
        plate.paste(star, (pad, pad), star)

        px, py = (w - plate.size[0]) // 2, (h - plate.size[1]) // 2
        im.paste(plate, (px, py))

    im.save(out)
    print(f"{out}  {im.size[0]}x{im.size[1]}  версия {qr.version}, коррекция {qr.error.upper()}")
    print(f"  ссылка: {url}, поле {field} {light}")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://inayasreda.ru/"
    out = sys.argv[2] if len(sys.argv) > 2 else "deck/qr-site.png"
    make(url, out, sys.argv[3] if len(sys.argv) > 3 else "deck")
