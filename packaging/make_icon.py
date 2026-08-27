from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    out = Path(__file__).resolve().parent / "icon.ico"
    img = Image.new("RGBA", (256, 256), (20, 17, 14, 255))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((28, 28, 228, 228), radius=40, fill=(28, 24, 19, 255))
    draw.rounded_rectangle((28, 28, 228, 228), radius=40, outline=(201, 212, 162, 255), width=10)
    draw.ellipse((104, 78, 152, 126), fill=(201, 212, 162, 255))
    draw.rectangle((118, 122, 138, 186), fill=(201, 212, 162, 255))
    img.save(
        out,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(out)


if __name__ == "__main__":
    main()
