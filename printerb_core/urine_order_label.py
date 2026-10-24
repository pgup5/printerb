"""Large, two-line instruction label for requesting a urine order."""

from PIL import Image, ImageDraw


LINES = ("報到後，敲門和護理師", "說：「要開驗尿單」")


def render_urine_order_label(*, size, margins, font_loader):
    left, top, right, bottom = margins
    width, height = size[0] - left - right, size[1] - top - bottom
    image = Image.new("1", size, 1)
    draw = ImageDraw.Draw(image)
    gap = 8
    for font_size in range(height, 0, -1):
        font = font_loader(font_size)
        boxes = [draw.textbbox((0, 0), line, font=font) for line in LINES]
        ink_height = sum(box[3] - box[1] for box in boxes)
        if ink_height + gap <= height and all(box[2] - box[0] <= width for box in boxes):
            break
    else:
        raise ValueError("Label is too small for urine order instructions")
    # Spread the two lines through the available height, with equal outer space.
    gap = max(gap, (height - ink_height) // 3)
    y = top + (height - ink_height - gap) // 2
    for line, box in zip(LINES, boxes):
        x = left + (width - (box[2] - box[0])) // 2
        draw.text((x - box[0], y - box[1]), line, font=font, fill=0)
        y += box[3] - box[1] + gap
    return image
