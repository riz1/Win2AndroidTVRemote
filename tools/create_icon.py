"""Rebuild the app icon with Pillow (development only; no runtime dependency)."""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "assets"
OUT.mkdir(exist_ok=True)
SCALE = 4


def box(coords):
    return tuple(round(v * SCALE) for v in coords)


image = Image.new("RGBA", (256 * SCALE, 256 * SCALE))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle(box((5, 5, 251, 251)), radius=54 * SCALE, fill="#182333")
draw.rounded_rectangle(box((13, 13, 243, 243)), radius=48 * SCALE,
                       outline="#30465f", width=2 * SCALE)
# A pale remote on a dark tile: recognizable even at taskbar size.
remote = Image.new("RGBA", image.size)
pen = ImageDraw.Draw(remote)
pen.rounded_rectangle(box((82, 25, 182, 236)), radius=43 * SCALE, fill="#0c1421")
pen.rounded_rectangle(box((76, 18, 176, 229)), radius=43 * SCALE, fill="#dce9fc")
pen.rounded_rectangle(box((82, 24, 170, 223)), radius=38 * SCALE, fill="#f1f6ff")
pen.ellipse(box((115, 37, 137, 59)), fill="#e76f72")
pen.ellipse(box((91, 76, 161, 146)), fill="#25364d")
pen.ellipse(box((111, 96, 141, 126)), fill="#77aaff")
for x, y in [(126, 84), (126, 138), (99, 111), (153, 111)]:
    pen.ellipse(box((x-2, y-2, x+2, y+2)), fill="#e7f0ff")
pen.rounded_rectangle(box((96, 163, 120, 174)), radius=5 * SCALE, fill="#9aaec9")
pen.rounded_rectangle(box((132, 163, 156, 174)), radius=5 * SCALE, fill="#9aaec9")
pen.rounded_rectangle(box((103, 190, 149, 202)), radius=6 * SCALE, fill="#77aaff")
image.alpha_composite(remote.rotate(-20, resample=Image.Resampling.BICUBIC))
image = image.resize((256, 256), Image.Resampling.LANCZOS)
image.save(OUT / "remote.png")
image.save(OUT / "remote.ico", sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
print(f"Created icons in {OUT}")
