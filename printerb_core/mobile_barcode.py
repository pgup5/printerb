"""Taiwan e-invoice carrier labels, using Code 39 without a check digit.

Format reference: https://www.einvoice.nat.gov.tw/static/ptl/ein_upload/download/2173.pdf
"""

import re

from PIL import Image, ImageDraw


def validate_mobile_barcode(value: object) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"/[A-Z0-9+.-]{7}", text):
        raise ValueError("手機條碼須為 8 碼：/ 開頭，後接 7 碼大寫英文、數字或 + - .，例如 /ABC1234。")
    return text


def code39_pattern(value: str) -> str:
    from reportlab.graphics.barcode.code39 import Standard39

    barcode = Standard39(validate_mobile_barcode(value), checksum=False, stop=True, ratio=3)
    barcode._calculate()
    return barcode.decomposed


def render_mobile_barcode(value, *, size, margins, font_loader) -> Image.Image:
    """Use 70% of the content height for bars and 30% for readable text."""
    text = validate_mobile_barcode(value)
    left, top, right, bottom = margins
    width = size[0] - left - right
    height = size[1] - top - bottom
    bar_area_height = round(height * 0.7)
    text_area_height = height - bar_area_height
    pattern = code39_pattern(text)
    widths = [3 if symbol in "BS" else 1 for symbol in pattern]
    # Ten narrow modules of quiet space on each side, with integer pixel bars.
    module_width = width // (sum(widths) + 20)
    if module_width < 2:
        raise ValueError("標籤寬度不足，無法產生清晰的手機條碼。")
    image = Image.new("1", size, color=1)
    draw = ImageDraw.Draw(image)
    x = left + (width - sum(widths) * module_width) // 2
    for symbol, modules in zip(pattern, widths):
        pixels = modules * module_width
        if symbol in "bB":
            draw.rectangle((x, top, x + pixels - 1, top + bar_area_height - 5), fill=0)
        x += pixels
    for font_size in range(text_area_height, 7, -1):
        font = font_loader(font_size)
        box = draw.textbbox((0, 0), text, font=font)
        text_width, text_height = box[2] - box[0], box[3] - box[1]
        if text_width <= width and text_height <= text_area_height - 4:
            break
    else:
        raise ValueError("手機條碼文字無法放入標籤。")
    x = left + (width - text_width) // 2 - box[0]
    y = top + bar_area_height + (text_area_height - text_height) // 2 - box[1]
    draw.text((x, y), text, font=font, fill=0)
    return image
