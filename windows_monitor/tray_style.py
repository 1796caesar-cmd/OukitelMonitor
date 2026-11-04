"""Large, bold white charge percentage for the Windows notification area.

No battery shape, no colored backing, no circle or border. Windows determines
actual icon size (often 16-24 px), which the application cannot enlarge.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont


def _font(size: int):
    # Prefer narrow bold faces so 100% stays legible at tray sizes.
    candidates = (
        r"C:\Windows\Fonts\ARIALNB.TTF",  # Arial Narrow Bold
        r"C:\Windows\Fonts\arialbd.ttf",
        "DejaVuSansCondensed-Bold.ttf",
        "DejaVuSans-Bold.ttf",
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def tray_image(level: int | None, stale: bool = False) -> Image.Image:
    """Transparent square with maximum-size, high-contrast white text '90%'.

    The last known value is kept even when stale. Status remains in tooltip.
    """
    scale = 4
    size = 64 * scale
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    label = "--" if level is None else f"{max(0, min(100, int(level)))}%"
    font = _font(100)
    margin = 1 * scale
    for pt in range(225, 30, -1):
        candidate = _font(pt)
        bounds = draw.textbbox((0, 0), label, font=candidate)
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        if width <= size - margin * 2 and height <= size - margin * 2:
            font = candidate
            break
    box = draw.textbbox((0, 0), label, font=font)
    x = (size - (box[2] - box[0])) / 2 - box[0]
    y = (size - (box[3] - box[1])) / 2 - box[1]
    # Dark micro-outline is only around letters, not a background or frame.
    draw.text((x, y), label, font=font, fill=(255, 255, 255, 255),
              stroke_width=2 * scale, stroke_fill=(0, 0, 0, 210))
    return icon.resize((64, 64), Image.Resampling.LANCZOS)
