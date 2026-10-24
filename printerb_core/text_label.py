"""Fit custom multiline text into a label's printable area."""

from PIL import Image, ImageDraw

from .collection_label import _wrap


def render_text_label(text, *, size, margins, font_loader):
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ").strip()
    if not text:
        raise ValueError("請輸入標籤文字。")
    left, top, right, bottom = margins
    width, height = size[0] - left - right, size[1] - top - bottom
    image = Image.new("1", size, 1)
    draw = ImageDraw.Draw(image)
    for font_size in range(2 * max(width, height), 0, -1):
        font = font_loader(font_size)
        lines = _wrap(draw, text, font, width)
        if lines is None:
            continue
        boxes = [draw.textbbox((0, 0), line or "Ag", font=font) for line in lines]
        gap = max(2, font_size // 10)
        total = sum(box[3] - box[1] for box in boxes) + gap * (len(lines) - 1)
        if total <= height and all(box[2] - box[0] <= width for box in boxes):
            break
    else:
        raise ValueError("文字過多，請縮短標籤內容。")
    y = top + (height - total) // 2
    for line, box in zip(lines, boxes):
        draw.text((left - box[0], y - box[1]), line, font=font, fill=0)
        y += box[3] - box[1] + gap
    return image
