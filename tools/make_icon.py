"""生成应用图标 assets/app.ico（极简：深色圆角方块 + 白色书签）。

用法： .venv\\Scripts\\python.exe tools\\make_icon.py
依赖 Pillow（若项目 venv 未装，用 hermes venv 跑即可）。
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "app.ico"

BG = (28, 28, 32, 255)
FG = (242, 242, 247, 255)


def render(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 圆角底
    radius = max(1, int(size * 0.23))
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=BG)

    # 书签：矩形 + 底部 V 形缺口
    left = size * 0.32
    right = size * 0.68
    top = size * 0.24
    bottom = size * 0.78
    notch = (bottom - top) * 0.22
    draw.polygon(
        [
            (left, top),
            (right, top),
            (right, bottom),
            ((left + right) / 2, bottom - notch),
            (left, bottom),
        ],
        fill=FG,
    )
    return img


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    base = render(256)
    base.save(
        OUT,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("saved", OUT, OUT.stat().st_size, "bytes")

    # 顺带存一张 png，方便预览
    png = OUT.with_name("app.png")
    base.save(png)
    print("saved", png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
