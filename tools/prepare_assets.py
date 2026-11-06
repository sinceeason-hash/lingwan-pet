"""Prepare the supplied rabbit-ear photo without changing the original pixels."""
from pathlib import Path
import hashlib
import json
import math
import sys

import numpy as np
from PIL import Image, ImageOps, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def main():
    (ROOT / "validation").mkdir(parents=True, exist_ok=True)
    source = ASSETS / "original.png"
    src = ImageOps.exif_transpose(Image.open(source)).convert("RGB")
    # Trace this photo's silhouette to exclude the pink shirt behind the head.
    # Supersampling keeps the low-resolution outline soft without fading ears.
    contour = [
        (78,3),(133,3),(147,9),(161,20),(176,33),(187,46),(195,51),
        (205,44),(218,37),(234,33),(251,32),(269,34),(277,35),
        (277,3),(339,3),(334,14),(326,24),(316,32),(332,40),(345,51),
        (357,65),(367,80),(378,102),(384,124),(386,142),(392,143),
        (400,149),(405,161),(407,174),(406,189),(401,202),(395,210),
        (397,230),(400,247),(402,265),(417,267),(433,271),(450,277),
        (466,285),(478,295),(481,305),(479,316),(476,323),(494,323),
        (494,381),(185,381),(193,370),(210,357),(226,347),(247,337),
        (260,333),(250,321),(240,311),(229,300),(220,289),(212,279),
        (206,268),(202,258),(198,246),(194,234),(190,222),(184,209),
        (175,200),(171,183),(169,178),(163,180),
        (160,171),(170,166),(165,151),(163,137),(162,123),(165,110),
        (170,96),(176,84),(166,80),(151,75),(137,67),(123,57),
        (109,43),(97,29),(86,13),
    ]
    fine = Image.new("L", (src.width * 4, src.height * 4))
    ImageDraw.Draw(fine).polygon([(round(x * 4), round(y * 4)) for x, y in contour], fill=255)
    alpha = fine.resize(src.size, Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(.35))
    a = np.asarray(alpha).copy()
    a[a < 18] = 0
    a[a > 245] = 255
    alpha = Image.fromarray(a)
    alpha.save(ROOT / "validation" / "alpha.png")
    cutout = src.convert("RGBA")
    cutout.putalpha(alpha)
    box = alpha.getbbox()
    cutout = cutout.crop(box)
    cutout = ImageOps.expand(cutout, border=(20, 5, 20, 5), fill=(0, 0, 0, 0))
    cutout.save(ASSETS / "character.png")
    preview = Image.new("RGB", (cutout.width * 2, cutout.height), "#edf2f7")
    preview.paste("#272b36", (cutout.width, 0, cutout.width * 2, cutout.height))
    preview.paste(cutout, (0, 0), cutout)
    preview.paste(cutout, (cutout.width, 0), cutout)
    preview.save(ROOT / "validation" / "cutout_preview.jpg", quality=95)
    for i in range(12):
        phase = 2 * math.pi * i / 12
        frame = Image.new("RGBA", cutout.size)
        for y in range(cutout.height):
            lower = max(0, (y / cutout.height - 0.6) / 0.4)
            shift = round(math.sin(phase) * .025 * cutout.width * lower * lower)
            frame.paste(cutout.crop((0, y, cutout.width, y + 1)), (shift, y))
        frame.save(ASSETS / f"run_{i:02d}.png")
    icon = Image.new("RGBA", (256, 256), "#f7e5ee")
    face = cutout.crop((cutout.width * .07, 0, cutout.width * .86, cutout.height * .9))
    face.thumbnail((244, 244), Image.Resampling.LANCZOS)
    icon.paste(face, ((256 - face.width) // 2, 256 - face.height), face)
    mask = Image.new("L", (256, 256))
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 255, 255), radius=56, fill=255)
    icon.putalpha(mask)
    icon.save(ASSETS / "pet.ico", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
    icon.save(ASSETS / "icon.png")
    report = {"source_size": src.size, "cutout_size": cutout.size, "crop": box,
              "transparent_pixels": int((a == 0).sum()), "soft_edge_pixels": int(((a > 0) & (a < 255)).sum()),
              "method": "Photo-specific silhouette mask with supersampled soft edges", "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    (ROOT / "validation" / "asset_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
