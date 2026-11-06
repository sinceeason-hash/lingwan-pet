"""桌宠素材生成核心：抠图、裁剪、跑动帧、图标、应用换装。

供 pet_gui.py（内置窗口）和 tools/swap_character.py（命令行）共用。
只依赖 Pillow，可被 PyInstaller 打包进 exe。
"""
from __future__ import annotations

import math
import shutil
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

WORK_HEIGHT = 900          # 抠图后统一缩放到的目标高度
MAGIC = (255, 0, 255, 0)   # floodfill 用的哨兵颜色


def load_source(path) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGBA")


def has_real_alpha(img: Image.Image) -> bool:
    """判断图片是否自带可用的透明通道。"""
    alpha = img.getchannel("A")
    lo, hi = alpha.getextrema()
    return lo < 8 and hi > 247


def remove_background(img: Image.Image, tol: int = 30) -> Image.Image:
    """去掉与图片边缘相连的背景色（floodfill 连通法，支持渐变背景）。"""
    work = img.copy()
    w, h = work.size
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
             (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]
    for seed in seeds:
        px = work.getpixel(seed)
        if px == MAGIC or px[3] == 0:
            continue
        try:
            ImageDraw.floodfill(work, seed, MAGIC, thresh=tol)
        except Exception:
            pass
    work.putdata([p if p != MAGIC else (0, 0, 0, 0) for p in work.getdata()])
    return work


def smooth_alpha(img: Image.Image, erode: int = 1, blur: float = 0.8) -> Image.Image:
    """轻微腐蚀 + 模糊 alpha，去掉抠图边缘的白边/毛边。"""
    a = img.getchannel("A")
    if erode > 0:
        a = a.filter(ImageFilter.MinFilter(erode * 2 + 1))
    if blur > 0:
        a = a.filter(ImageFilter.GaussianBlur(blur))
    out = img.copy()
    out.putalpha(a)
    return out


def trim_and_pad(img: Image.Image, pad_ratio: float = 0.03) -> Image.Image:
    bbox = img.getchannel("A").getbbox()
    if bbox:
        img = img.crop(bbox)
    if img.width < 2 or img.height < 2:
        raise ValueError("图片主体为空，无法处理")
    pad_x = max(8, round(img.width * pad_ratio))
    pad_top = max(6, round(img.height * pad_ratio * 0.6))
    pad_bottom = max(10, round(img.height * pad_ratio))
    return ImageOps.expand(img, border=(pad_x, pad_top, pad_x, pad_bottom), fill=(0, 0, 0, 0))


def normalize_height(img: Image.Image, height: int = WORK_HEIGHT) -> Image.Image:
    if img.height <= height:
        return img
    scale = height / img.height
    return img.resize((round(img.width * scale), height), Image.Resampling.LANCZOS)


def opaque_ratio(img: Image.Image) -> float:
    w, h = img.size
    total = w * h
    if not total:
        return 0.0
    opaque = sum(1 for p in img.getchannel("A").getdata() if p > 10)
    return opaque / total


def make_run_frames(cutout: Image.Image) -> list[Image.Image]:
    """12 帧跑动摆姿：下半身按正弦相位扭动。"""
    frames = []
    for i in range(12):
        phase = 2 * math.pi * i / 12
        frame = Image.new("RGBA", cutout.size)
        for y in range(cutout.height):
            lower = max(0.0, (y / cutout.height - 0.6) / 0.4)
            shift = round(math.sin(phase) * 0.025 * cutout.width * lower * lower)
            frame.paste(cutout.crop((0, y, cutout.width, y + 1)), (shift, y))
        frames.append(frame)
    return frames


def make_icon(cutout: Image.Image) -> Image.Image:
    icon = Image.new("RGBA", (256, 256), "#f7e5ee")
    face = cutout.crop((round(cutout.width * .07), 0, round(cutout.width * .86), round(cutout.height * .9)))
    face.thumbnail((244, 244), Image.Resampling.LANCZOS)
    icon.paste(face, ((256 - face.width) // 2, 256 - face.height), face)
    mask = Image.new("L", (256, 256))
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 255, 255), radius=56, fill=255)
    icon.putalpha(mask)
    return icon


def backup_assets(assets_dir: Path) -> Path | None:
    names = ["character.png", "pet.ico", "icon.png"] + [f"run_{i:02d}.png" for i in range(12)]
    existing = [n for n in names if (assets_dir / n).exists()]
    if not existing:
        return None
    dest = assets_dir / f"backup_{time.strftime('%Y%m%d_%H%M%S')}"
    dest.mkdir(parents=True, exist_ok=True)
    for n in existing:
        shutil.move(str(assets_dir / n), str(dest / n))
    return dest


def apply_character(img: Image.Image, assets_dir: Path) -> Path:
    """把处理好的形象写入素材目录（含备份），返回 character.png 路径。

    调用前应确保 img 已是透明背景 RGBA；此函数会自动裁剪/缩放/生成帧与图标。
    """
    img = img.copy()
    if not has_real_alpha(img):
        img = smooth_alpha(remove_background(img, 30))
    img = normalize_height(trim_and_pad(img))
    backup_assets(assets_dir)
    img.save(assets_dir / "character.png")
    for i, frame in enumerate(make_run_frames(img)):
        frame.save(assets_dir / f"run_{i:02d}.png")
    icon = make_icon(img)
    icon.save(assets_dir / "pet.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.save(assets_dir / "icon.png")
    return assets_dir / "character.png"
