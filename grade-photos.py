"""Единый грейд для всех фото дека.

Снимки в scenario-photos/ сняты в разном свете и на разную технику.
Без общей обработки дек рассыпается, поэтому все проходят через один
пресет: подъём теней (проектор их не покажет), лёгкое обесцвечивание,
тауповый тон в полутонах и S-кривая на контраст.

Запуск:
    python3 grade-photos.py                      # все файлы
    python3 grade-photos.py scenario-photos/s15-01.jpg ...   # только указанные

Результат: deck/img/*.jpg
"""

import glob
import os
import sys

import numpy as np
from PIL import Image

TAUPE = np.array([135, 124, 107], float)
LONG_SIDE = 2000

# Доля высоты, которую нужно снять снизу после автообрезки интерфейса.
# У s11-02 в правом нижнем углу остаётся кнопка «звук выключен» из сториз:
# по насыщенности она от фотографии не отличается, поэтому задаётся руками.
BOTTOM_TRIM = {"s11-02.png": 0.12}


def crop_instagram(im, trim=0.0):
    """Отрезает интерфейс приложения от скриншота, оставляя только фото."""
    a = np.array(im.convert("RGB")).astype(float)
    mx, mn = a.max(axis=2), a.min(axis=2)
    rowsat = ((mx - mn) / (mx + 1e-6)).mean(axis=1)
    idx = np.where(rowsat > 0.15)[0]
    top, bot = int(idx.min()), int(idx.max())
    bot -= round((bot - top) * trim)
    print(f"    интерфейс обрезан, оставлены строки {top}..{bot}")
    return im.crop((0, top, im.size[0], bot + 1))


def grade(im):
    a = np.array(im.convert("RGB")).astype(float) / 255.0

    # тени: тёмное поднимается сильнее светлого
    a = a + 0.085 * (1.0 - a) ** 2.2

    lum = (a * np.array([0.2126, 0.7152, 0.0722])).sum(axis=2, keepdims=True)
    a = a * 0.86 + lum * 0.14

    # тауповый тон, максимум в полутонах
    t = TAUPE / 255.0
    weight = (1.0 - np.abs(lum - 0.5) * 2.0).clip(0, 1) * 0.13
    a = a * (1 - weight) + (lum * (t / t.mean())) * weight

    # S-кривая: возвращаем контраст, который съест проектор
    a = np.clip(a, 0, 1)
    a = a * a * (3 - 2 * a) * 0.30 + a * 0.70

    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))


def main():
    os.makedirs("deck/img", exist_ok=True)
    targets = sys.argv[1:] or sorted(glob.glob("scenario-photos/*"))
    for src in targets:
        name = os.path.basename(src)
        stem = os.path.splitext(name)[0]
        im = Image.open(src)
        if name in BOTTOM_TRIM:
            im = crop_instagram(im, BOTTOM_TRIM[name])
        w, h = im.size
        scale = LONG_SIDE / max(w, h)
        if scale < 1:
            im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
        out = grade(im)
        out.save(f"deck/img/{stem}.jpg", quality=88, optimize=True)
        print(f"{name} -> {stem}.jpg {out.size}")


if __name__ == "__main__":
    main()
