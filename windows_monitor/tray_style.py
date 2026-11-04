"""Minimal high-contrast percentage icon for Windows system tray.

White outline and white digits, transparent interior, no fill.  The native
64x64 image is downsampled by Windows to the current taskbar DPI.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont


def _font(size: int):
    for path in (r"C:\Windows\Fonts\arialbd.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def tray_image(level: int | None, stale: bool = False) -> Image.Image:
    """White outlined circle with a large percentage numeral, no solid fill.

    Staleness is shown in tooltip in the main app; do not hide the last known
    charge behind an unrequested color or filled background.
    """
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    WHITE = (255, 255, 255, 255)
    DARK = (0, 0, 0, 165)
    # Tiny dark backing stroke prevents the white ring from vanishing when the
    # user's Windows taskbar is bright.  The interior stays transparent.
    draw.ellipse((3, 3, 60, 60), outline=DARK, width=5)
    draw.ellipse((4, 4, 59, 59), outline=WHITE, width=4)

    label = "–" if level is None else str(max(0, min(100, int(level))))
    limit_width = 43
    font = _font(28 if len(label) == 2 else 23 if len(label) >= 3 else 36)
    for font_size in range(40 if len(label) == 1 else 32 if len(label) == 2 else 24, 15, -1):
        candidate = _font(font_size)
        box = draw.textbbox((0, 0), label, font=candidate, stroke_width=0)
        if box[2] - box[0] <= limit_width and box[3] - box[1] <= 33:
            font = candidate
            break
    box = draw.textbbox((0, 0), label, font=font)
    x = (size - (box[2] - box[0])) / 2 - box[0]
    y = (size - (box[3] - box[1])) / 2 - box[1] - 1
    draw.text((x, y), label, font=font, fill=WHITE, stroke_width=1, stroke_fill=DARK)
    return image
