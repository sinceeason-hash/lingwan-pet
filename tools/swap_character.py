"""一键换形象：把任意图片变成桌宠新形象。

用法（三选一）：
  1. 双击项目根目录的「一键换形象.bat」，在弹出的窗口里选图片
  2. 把图片文件直接拖到「一键换形象.bat」图标上
  3. 命令行：python tools/swap_character.py 图片路径 [--tol 30] [--height 900]

处理逻辑：
  - PNG 已带透明背景 → 直接使用，不做抠图
  - 其他图片 → 自动去除与边框相连的纯色/渐变背景（容差可用 --tol 调整）
  - 自动裁剪、留白，生成 character.png + 12 帧跑动图 + 应用图标
  - 旧素材自动备份到 assets/backup_时间戳/，并生成对比预览图供确认

只依赖 Pillow（不需要 numpy）。生成后重启桌宠即可看到新形象。
"""
from __future__ import annotations

import argparse
import math
import shutil
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
VALIDATION = ROOT / "validation"

WORK_HEIGHT = 900          # 抠图后统一缩放到的目标高度
MAGIC = (255, 0, 255, 0)   # floodfill 用的哨兵颜色


def load_source(path: Path) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGBA")


def has_real_alpha(img: Image.Image) -> bool:
    """判断图片是否自带可用的透明通道（存在全透明像素且不是全不透明）。"""
    alpha = img.getchannel("A")
    lo, hi = alpha.getextrema()
    return lo < 8 and hi > 247


def remove_background(img: Image.Image, tol: int) -> Image.Image:
    """去掉与图片边缘相连的背景色（floodfill 连通法，支持渐变背景）。"""
    work = img.copy()
    w, h = work.size
    seeds = []
    for x, y in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
                 (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
        seeds.append((x, y))
    # 依次从边缘种子点填充；已填充过的区域不会再扩散
    for seed in seeds:
        px = work.getpixel(seed)
        if px == MAGIC or px[3] == 0:
            continue
        try:
            ImageDraw.floodfill(work, seed, MAGIC, thresh=tol)
        except Exception:
            pass
    # 哨兵色 → 透明
    data = work.getdata()
    work.putdata([p if p != MAGIC else (0, 0, 0, 0) for p in data])
    return work


def smooth_alpha(img: Image.Image, erode: int = 1, blur: float = 1.0) -> Image.Image:
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
    pad_x = max(8, round(img.width * pad_ratio))
    pad_top = max(6, round(img.height * pad_ratio * 0.6))
    pad_bottom = max(10, round(img.height * pad_ratio))
    return ImageOps.expand(img, border=(pad_x, pad_top, pad_x, pad_bottom), fill=(0, 0, 0, 0))


def normalize_height(img: Image.Image, height: int = WORK_HEIGHT) -> Image.Image:
    if img.height <= height:
        return img
    scale = height / img.height
    return img.resize((round(img.width * scale), height), Image.Resampling.LANCZOS)


def make_run_frames(cutout: Image.Image) -> list[Image.Image]:
    """12 帧跑动摆姿：下半身按正弦相位扭动（与原 prepare_assets 逻辑一致）。"""
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


def checkerboard(size: tuple[int, int], cell: int = 16) -> Image.Image:
    board = Image.new("RGB", size, "#ffffff")
    d = ImageDraw.Draw(board)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if (x // cell + y // cell) % 2:
                d.rectangle((x, y, x + cell - 1, y + cell - 1), fill="#dfe3ea")
    return board


def make_preview(source: Image.Image, cutout: Image.Image, out: Path) -> None:
    """原图 | 抠图结果（棋盘底）并排预览图。"""
    target_h = 560
    def fit(im: Image.Image, bg) -> Image.Image:
        im = im.copy()
        im.thumbnail((target_h * 2, target_h), Image.Resampling.LANCZOS)
        canvas = bg((im.width + 24, target_h + 24))
        canvas.paste(im, (12, 12), im)
        return canvas
    left = fit(source, lambda s: Image.new("RGB", s, "#ffffff"))
    right = fit(cutout, lambda s: checkerboard(s))
    gap = 26
    header = 56
    total = Image.new("RGB", (left.width + right.width + gap * 3, target_h + header + 24), "#f4f1f8")
    d = ImageDraw.Draw(total)
    try:
        font = ImageFont.truetype("msyh.ttc", 22)
    except OSError:
        font = ImageFont.load_default()
    total.paste(left, (gap, header))
    total.paste(right, (left.width + gap * 2, header))
    d.text((gap, 16), "原图", fill="#332c42", font=font)
    d.text((left.width + gap * 2, 16), "抠图结果（透明区域为棋盘格）", fill="#332c42", font=font)
    total.save(out, quality=95)


def backup_old_assets() -> Path | None:
    names = ["character.png", "pet.ico", "icon.png"] + [f"run_{i:02d}.png" for i in range(12)]
    existing = [n for n in names if (ASSETS / n).exists()]
    if not existing:
        return None
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = ASSETS / f"backup_{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    for n in existing:
        shutil.move(str(ASSETS / n), str(dest / n))
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="一键更换桌宠形象")
    parser.add_argument("image", nargs="?", help="图片路径（不填则弹出文件选择框）")
    parser.add_argument("--tol", type=int, default=30, help="背景色容差 0-120，背景去不干净可调大（默认 30）")
    parser.add_argument("--no-erode", action="store_true", help="不做边缘腐蚀（白边明显时别用此项，改用默认）")
    args = parser.parse_args()

    path_str = args.image
    if not path_str:
        try:
            import tkinter as tk
            from tkinter import filedialog
            tk.Tk().withdraw()
            path_str = filedialog.askopenfilename(
                title="选择桌宠新形象图片（建议透明 PNG 或纯色背景图）",
                filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp"), ("所有文件", "*.*")])
        except Exception:
            print("无法打开文件选择框，请用命令行传入图片路径。")
            return 1
    if not path_str:
        print("未选择图片，已退出。")
        return 0

    src_path = Path(path_str)
    if not src_path.exists():
        print(f"找不到图片：{src_path}")
        return 1

    print(f"读取图片：{src_path.name}")
    src = load_source(src_path)
    VALIDATION.mkdir(parents=True, exist_ok=True)

    if has_real_alpha(src):
        print("检测到透明背景 PNG，直接使用，不做抠图。")
        cutout = src
    else:
        print(f"自动去背景中（容差 tol={args.tol}）…")
        cutout = remove_background(src, args.tol)
        if not args.no_erode:
            cutout = smooth_alpha(cutout, erode=1, blur=0.8)
        covered = sum(1 for p in cutout.getchannel("A").getdata() if p > 10)
        if covered < cutout.width * cutout.height * 0.02:
            print("警告：去背景后主体几乎为空！背景可能不是纯色，"
                  "建议改用透明 PNG，或调大 --tol 再试。")
            return 1

    cutout = trim_and_pad(cutout)
    cutout = normalize_height(cutout)
    print(f"主体尺寸：{cutout.width} x {cutout.height}")

    print("生成 12 帧跑动图…")
    frames = make_run_frames(cutout)
    print("生成应用图标…")
    icon = make_icon(cutout)

    backup = backup_old_assets()
    if backup:
        print(f"旧形象已备份到：{backup.name}/")

    cutout.save(ASSETS / "character.png")
    for i, frame in enumerate(frames):
        frame.save(ASSETS / f"run_{i:02d}.png")
    icon.save(ASSETS / "pet.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.save(ASSETS / "icon.png")

    preview = VALIDATION / "换形象_预览.png"
    make_preview(src, cutout, preview)

    print("\n完成！新形象已写入 assets/。")
    print(f"预览图：{preview}")
    print("如果桌宠正在运行，退出后重新启动即可看到新形象。")
    try:
        import os
        os.startfile(preview)  # Windows: 自动打开预览供确认
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
