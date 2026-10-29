"""Patient fields: 50% name, 25% ID, 25% birthday."""

from datetime import datetime
from PIL import Image, ImageDraw, ImageOps


def format_birthday(birthday):
    text = str(birthday).strip()
    datetime.strptime(text, "%Y/%m/%d")
    return text


def render(name, birthday, patient_id, *, size, margins, font_loader):
    name, patient_id = str(name or "").strip(), str(patient_id or "").strip()
    if not name or not patient_id or not birthday:
        raise ValueError("姓名、身分證字號及生日皆為必填。")
    lines = (name, patient_id, format_birthday(birthday))
    if any("\n" in line or "\r" in line or "\t" in line for line in lines):
        raise ValueError("姓名、身分證字號及生日須為單行文字。")
    left, top, right, bottom = margins
    width, height = size[0] - left - right, size[1] - top - bottom
    image = Image.new("1", size, 1)
    draw = ImageDraw.Draw(image)
    rows = ((0, height // 2),
            (height // 2, height * 3 // 4),
            (height * 3 // 4, height))
    for index, text in enumerate(lines):
        start, end = rows[index]
        row_height = end - start
        for font_size in range(2 * max(width, row_height), 0, -1):
            font = font_loader(font_size)
            box = draw.textbbox((0, 0), text, font=font)
            if box[2] - box[0] <= width and box[3] - box[1] <= row_height - 4:
                break
        else:
            raise ValueError("病人資料過長，無法容納於標籤。")
        line = Image.new("1", (box[2] - box[0], box[3] - box[1]), 1)
        ImageDraw.Draw(line).text((-box[0], -box[1]), text, font=font, fill=0)
        ink_bounds = ImageOps.invert(line.convert("L")).getbbox()
        if ink_bounds:
            line = line.crop(ink_bounds)
            y = top + start + (row_height - line.height) // 2
            image.paste(line, (left, y))
    return image
