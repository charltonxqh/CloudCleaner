"""Generate the CloudCleaner pixel logo as SVG and PNG.

Pixel art, so PNGs are written by hand (zlib + struct) with nearest-neighbour
scaling — an SVG rasteriser would antialias the edges and lose the pixels.

    python3 scripts/make_logo.py
"""

import struct
import zlib
from pathlib import Path

SIZE = 24
OUT = Path(__file__).resolve().parent.parent / "public"

# Two lobes rather than one arc, so it reads as a cloud and not a rock.
CLOUD = (
    [(4, 7), (5, 7)]
    + [(x, 8) for x in range(3, 7)] + [(9, 8), (10, 8)]
    + [(x, 9) for x in range(2, 12)]
    + [(x, 10) for x in range(1, 13)]
    + [(x, 11) for x in range(1, 13)]
    + [(x, 12) for x in range(2, 12)]
)
# A two-pixel shine in the upper left, the way pixel art usually fakes volume.
SHADE = [(3, 9), (4, 8)]
HANDLE = [(21, 1), (21, 2), (21, 3), (20, 4), (20, 5), (19, 6), (19, 7), (18, 8)]
BINDING = [(17, 9), (18, 9), (19, 9)]
BRISTLES = (
    [(x, 10) for x in range(16, 21)]
    + [(x, 11) for x in range(15, 22)]
    + [(x, 12) for x in range(15, 22)]
)
TIPS = [(15, 13), (17, 13), (19, 13), (21, 13)]
MOTES = [(6, 16), (10, 17), (13, 16), (16, 15)]

# (pixels, svg fill, opacity, rgb for png)
#
# Two variants. WHITE is for dark slides and the app sidebar; INK is for light
# slides and print. The shine flips direction between them: a lighter patch is
# invisible on a white cloud, so there it becomes a soft grey instead.
LAYERS_WHITE = [
    (CLOUD, "currentColor", None, (255, 255, 255)),
    (SHADE, "#c9cdd4", None, (201, 205, 212)),
    (HANDLE, "var(--logo-wood, #c08b4e)", None, (192, 139, 78)),
    (BINDING, "var(--logo-band, #8a5f2e)", None, (138, 95, 46)),
    (BRISTLES + TIPS, "var(--logo-straw, #f0cf5a)", None, (240, 207, 90)),
    (MOTES, "#ffffff", "0.6", (255, 255, 255)),
]
LAYERS_INK = [
    (CLOUD, "#191919", None, (25, 25, 25)),
    (SHADE, "#5a5c63", None, (90, 92, 99)),
    (HANDLE, "#a8703c", None, (168, 112, 60)),
    (BINDING, "#6b4a26", None, (107, 74, 38)),
    (BRISTLES + TIPS, "#d9a91f", None, (217, 169, 31)),
    (MOTES, "#191919", "0.35", (150, 150, 150)),
]

# kept for callers that used the old names
LAYERS_DARK_BG = LAYERS_WHITE
LAYERS_LIGHT_BG = LAYERS_INK


def _centre():
    """Shift every layer so the art sits centred in the grid.

    Coordinates are authored by hand, so the drawing drifts as pixels are added
    or removed. Centring here keeps the exports balanced without anyone having
    to re-tune the numbers.
    """
    everything = [p for layer in LAYERS_INK for p in layer[0]]
    xs = [x for x, _ in everything]
    ys = [y for _, y in everything]
    dx = (SIZE - (max(xs) - min(xs) + 1)) // 2 - min(xs)
    dy = (SIZE - (max(ys) - min(ys) + 1)) // 2 - min(ys)

    if not dx and not dy:
        return
    for group in (CLOUD, SHADE, HANDLE, BINDING, BRISTLES, TIPS, MOTES):
        group[:] = [(x + dx, y + dy) for x, y in group]


_centre()


def svg_rects(layers):
    out = []
    for pixels, fill, opacity, _ in layers:
        o = f' opacity="{opacity}"' if opacity else ""
        for x, y in pixels:
            out.append(f'  <rect x="{x}" y="{y}" width="1" height="1" fill="{fill}"{o}/>')
    return "\n".join(out)


def write_svgs():
    for name, layers in (("logo.svg", LAYERS_WHITE), ("logo-ink.svg", LAYERS_INK)):
        (OUT / name).write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}"\n'
            f'     shape-rendering="crispEdges" role="img" aria-label="CloudCleaner">\n'
            f"  <title>CloudCleaner</title>\n{svg_rects(layers)}\n</svg>\n"
        )
    (OUT / "logo-wordmark.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 172 24"\n'
        f'     shape-rendering="crispEdges" role="img" aria-label="CloudCleaner">\n'
        f"  <title>CloudCleaner</title>\n  <g>\n{svg_rects(LAYERS_LIGHT_BG)}\n  </g>\n"
        f'  <text x="30" y="17" font-family="Fira Sans, system-ui, sans-serif"\n'
        f'        font-size="16" font-weight="700" letter-spacing="-.3" fill="#191919"\n'
        f'        shape-rendering="auto">CloudCleaner</text>\n</svg>\n'
    )


def png(path, layers, scale, background=None):
    """Minimal RGBA PNG writer. Nearest-neighbour, so pixels stay square."""
    w = h = SIZE * scale
    canvas = [[background or (0, 0, 0, 0)] * w for _ in range(h)]

    for pixels, _, opacity, rgb in layers:
        alpha = int(255 * float(opacity)) if opacity else 255
        for x, y in pixels:
            for dy in range(scale):
                for dx in range(scale):
                    canvas[y * scale + dy][x * scale + dx] = (*rgb, alpha)

    raw = b"".join(
        b"\x00" + b"".join(struct.pack("4B", *px) for px in row) for row in canvas
    )

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">2I5B", w, h, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    write_svgs()

    # Large enough that nothing has to be scaled up. 24px art at scale 128 is
    # 3072px square, which is past anything a slide or a poster needs.
    for scale in (21, 64, 128):
        size = SIZE * scale
        png(OUT / f"logo-white-{size}.png", LAYERS_WHITE, scale)
        png(OUT / f"logo-ink-{size}.png", LAYERS_INK, scale)

    png(OUT / "logo-onblack-3072.png", LAYERS_WHITE, 128, background=(25, 25, 25, 255))
    png(OUT / "logo-72.png", LAYERS_INK, 3)

    for f in sorted(OUT.glob("logo*")):
        print(f"  {f.name:28} {f.stat().st_size // 1024:>5} KB")
