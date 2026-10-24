"""Render patient identification and a collection reason in 30% label height."""

from PIL import Image, ImageDraw


def _wrap(draw, text, font, width):
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for char in paragraph:
            candidate = line + char
            box = draw.textbbox((0, 0), candidate, font=font)
            if box[2] - box[0] > width:
                if not line:
                    return None
                lines.append(line)
                line = char
            else:
                line = candidate
        lines.append(line)
    return lines


def _fit(draw, text, width, height, font_loader, wrap):
    for size in range(height, 7, -1):
        font = font_loader(size)
        lines = _wrap(draw, text, font, width) if wrap else [text]
        if lines is None:
            continue
        boxes = [draw.textbbox((0, 0), line or "Ag", font=font) for line in lines]
        total_height = sum(b[3] - b[1] for b in boxes) + 2 * (len(lines) - 1)
        if total_height <= height and all(b[2] - b[0] <= width for b in boxes):
            return font, lines, boxes
    raise ValueError("收集標籤內容過長，請縮短 Reason 或病人資料。")


def render_collection_label(name, mrn, reason, *, size, margins, font_loader):
    name = str(name or "").strip()
    mrn = str(mrn or "").strip()
    reason = str(reason or "").strip().replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    if not name or not mrn or not reason:
        raise ValueError("收集標籤需要姓名、病歷號及 Reason。")
    if any(char in name + mrn for char in "\r\n\t"):
        raise ValueError("姓名與病歷號須為單行文字。")
    left, top, right, bottom = margins
    width = size[0] - left - right
    block_height = round(size[1] * 0.3)
    if block_height > size[1] - top - bottom:
        raise ValueError("標籤邊界超出可列印範圍。")
    first_height = block_height // 2
    image = Image.new("1", size, color=1)
    draw = ImageDraw.Draw(image)
    for text, y, height, wrap in (
        (f"{name}    {mrn}", top, first_height, False),
        (reason, top + first_height, block_height - first_height, True),
    ):
        font, lines, boxes = _fit(draw, text, width, height - 2, font_loader, wrap)
        for line, box in zip(lines, boxes):
            draw.text((left - box[0], y - box[1]), line, font=font, fill=0)
            y += box[3] - box[1] + 2
    return image
