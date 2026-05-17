"""Generate a 512x512 source icon for the jr-dashboard Tauri app.

After running this, use:
    cd desktop/frontend && npx tauri icon ../icon-source.png
to generate all required Tauri icon formats (32x32.png, 128x128.png, 256x256.png, .ico, .icns).
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "icon-source.png"
SIZE = 512

# Colors matching app theme
BG_OUTER = (11, 14, 20)       # --color-bg
BG_INNER = (19, 24, 34)        # --color-panel
ACCENT   = (56, 189, 248)      # --color-accent
UP       = (34, 197, 94)
DOWN     = (239, 68, 68)
MUTED    = (148, 163, 184)

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# Rounded background
R = 96
d.rounded_rectangle((0, 0, SIZE, SIZE), R, fill=BG_OUTER, outline=ACCENT, width=8)

# Inner gradient-like circle
center = SIZE // 2
d.rounded_rectangle((48, 48, SIZE - 48, SIZE - 48), R - 24, fill=BG_INNER)

# Small candlesticks suggesting price action
candles = [
    # (x_center, body_top, body_bottom, wick_top, wick_bottom, up?)
    (140,  300, 360,  280, 380,  False),
    (210,  240, 320,  220, 340,  True),
    (280,  180, 280,  160, 300,  True),
    (350,  140, 220,  120, 240,  True),
]
for x, bt, bb, wt, wb, up in candles:
    color = UP if up else DOWN
    # wick
    d.line([(x, wt), (x, wb)], fill=color, width=4)
    # body
    body_left, body_right = x - 16, x + 16
    d.rectangle((body_left, bt, body_right, bb), fill=color)

# "jr" text bottom-right
try:
    font = ImageFont.truetype("arial.ttf", 100)
except OSError:
    font = ImageFont.load_default()
d.text((SIZE - 200, SIZE - 180), "jr", fill=ACCENT, font=font)

# small upward arrow as accent
arrow_y = SIZE - 100
d.polygon([(70, arrow_y), (90, arrow_y - 20), (90, arrow_y - 10), (130, arrow_y - 10),
           (130, arrow_y + 10), (90, arrow_y + 10), (90, arrow_y + 20)], fill=ACCENT)

img.save(OUT, "PNG")
print(f"wrote {OUT}  ({img.size})")
