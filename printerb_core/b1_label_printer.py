"""Render and print 50 x 30 mm growth labels on a USB NIIMBOT B1.

The NIIMBOT packet protocol is adapted from niimbot/niimprintx:
https://github.com/niimbot/niimprintx

MIT License

Copyright (c) 2023 kjy00302

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
import logging
import math
import sys
from pathlib import Path
import re
import struct
import time
from typing import Iterable, Mapping

from PIL import Image, ImageDraw, ImageFont, ImageOps
import serial
from serial.tools import list_ports

try:
    from .growth import format_percentile_display
except ImportError:
    from growth import format_percentile_display

LABEL_SIZE = (384, 240)
DEFAULT_DENSITY = 3
LABEL_FOOTER = "天成醫院 詹豐燦醫師"
_B1_PRINT_START = struct.pack(">H4xB", 1, 0)
_B1_PAGE_COPIES = 1
_B1_STATUS_POLL_LIMIT = 50
_B1_STATUS_POLL_INTERVAL = 0.2
logger = logging.getLogger(__name__)
_AGE_PATTERN = re.compile(r"^(\d+)y(\d+)m$", re.IGNORECASE)
_NIIMBOT_HINTS = ("niimbot", "b1", "usb serial", "ch340", "cp210", "wch")
_FONT_CANDIDATES = (
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    Path("/usr/share/fonts/truetype/arphic/ukai.ttc"),
    Path(r"C:\Windows\Fonts\msjh.ttc"),
    Path(r"C:\Windows\Fonts\msjhbd.ttc"),
    Path(r"C:\Windows\Fonts\mingliu.ttc"),
    Path(r"C:\Windows\Fonts\kaiu.ttf"),
    Path(r"C:\Windows\Fonts\NotoSansTC-Regular.otf"),
)


class LabelPrinterError(RuntimeError):
    """Base error raised by this module."""


class PrinterNotFoundError(LabelPrinterError):
    """Raised when a NIIMBOT serial port cannot be selected safely."""


class PrinterCommunicationError(LabelPrinterError):
    """Raised when the printer does not acknowledge a command."""


def available_serial_ports():
    """Return the serial ports currently reported by pyserial."""
    return list(list_ports.comports())


def find_niimbot_port(port: str | None = None) -> str:
    """Select a likely NIIMBOT port, or validate an explicitly supplied port."""
    ports = available_serial_ports()
    if port:
        for candidate in ports:
            if candidate.device.casefold() == port.casefold():
                return candidate.device
        detected = ", ".join(item.device for item in ports) or "none"
        raise PrinterNotFoundError(
            f"Serial port {port!r} was not found. Detected ports: {detected}."
        )

    if not ports:
        raise PrinterNotFoundError(
            "No serial ports were detected. Connect and power on the NIIMBOT B1."
        )
    if len(ports) == 1:
        return ports[0].device

    likely = []
    for candidate in ports:
        details = " ".join(
            str(value or "")
            for value in (
                candidate.description,
                candidate.manufacturer,
                candidate.product,
                candidate.hwid,
            )
        ).casefold()
        if any(hint in details for hint in _NIIMBOT_HINTS):
            likely.append(candidate)
    if len(likely) == 1:
        return likely[0].device

    descriptions = "; ".join(
        f"{item.device} ({item.description or 'unknown device'})" for item in ports
    )
    raise PrinterNotFoundError(
        "Could not choose the NIIMBOT port uniquely. "
        f"Detected: {descriptions}. Select a port explicitly "
        "(for example /dev/ttyUSB0 on Linux or COM4 on Windows)."
    )


def parse_age(age: str) -> int:
    """Convert the application's XyYm age value to total completed months."""
    if not isinstance(age, str) or not (match := _AGE_PATTERN.fullmatch(age.strip())):
        raise ValueError(f"Invalid age {age!r}; expected a value such as '2y6m'.")
    years, months = (int(value) for value in match.groups())
    if months >= 12:
        raise ValueError(f"Invalid age {age!r}; months must be between 0 and 11.")
    return years * 12 + months


def format_age_for_label(age: str) -> str:
    """Format the existing XyYm age for Traditional Chinese label display."""
    total_months = parse_age(age)
    years, months = divmod(total_months, 12)
    return f"{years}歲{months}月"


def format_percentile(value: object) -> str:
    """Normalize numeric and legacy percentile values for label display."""
    text = str(value or "").strip()
    if not text:
        return "-"

    match = re.fullmatch(
        r"([<>]?)\s*(?:第)?\s*(\d+(?:\.\d+)?)\s*"
        r"(?:(?:st|nd|rd|th)\s*)?(?:百分位)?",
        text,
        re.IGNORECASE,
    )
    if match:
        marker, numeric_text = match.groups()
        if marker == "<":
            return "<第3百分位"
        if marker == ">":
            return ">第97百分位"
        return format_percentile_display(float(numeric_text))
    return text


def build_growth_label_lines(
    user_data: Mapping[str, object], *, examination_date: date | None = None
) -> list[str]:
    """Build the four display lines from the application's existing user_data."""
    age = str(user_data.get("age", "")).strip()
    age_months = parse_age(age)
    display_age = format_age_for_label(age)
    today = (examination_date or date.today()).strftime("%Y/%m/%d")
    height = str(user_data.get("body_height", "") or "-").strip()
    weight = str(user_data.get("body_weight", "") or "-").strip()
    lines = [
        f"檢查日期：{today}",
        f"年齡：{display_age}",
        f"身高：{height}cm  {format_percentile(user_data.get('height_percentile'))}",
        f"體重：{weight}kg  {format_percentile(user_data.get('weight_percentile'))}",
    ]
    if age_months < 36:
        head = str(user_data.get("head_circumference", "") or "-").strip()
        lines.append(
            f"頭圍：{head}cm  "
            f"{format_percentile(user_data.get('head_circumference_percentile'))}"
        )
    else:
        bmi = str(user_data.get("BMI", "") or "-").strip()
        interpretation = str(user_data.get("bmi_interpretation", "") or "-").strip()
        lines.append(f"BMI：{bmi}  體位：{interpretation}")
    lines.append(LABEL_FOOTER)
    return lines


def _build_growth_body_rows(
    user_data: Mapping[str, object], age_months: int
) -> list[tuple[str, str, str]]:
    """Return label, value, and suffix columns for the three measurement rows."""
    height = str(user_data.get("body_height", "") or "-").strip()
    weight = str(user_data.get("body_weight", "") or "-").strip()
    rows = [
        ("身高：", f"{height}cm", format_percentile(user_data.get("height_percentile"))),
        ("體重：", f"{weight}kg", format_percentile(user_data.get("weight_percentile"))),
    ]
    if age_months < 36:
        head = str(user_data.get("head_circumference", "") or "-").strip()
        rows.append(
            (
                "頭圍：",
                f"{head}cm",
                format_percentile(user_data.get("head_circumference_percentile")),
            )
        )
    else:
        bmi = str(user_data.get("BMI", "") or "-").strip()
        interpretation = str(user_data.get("bmi_interpretation", "") or "-").strip()
        rows.append(("BMI：", bmi, f"體位：{interpretation}"))
    return rows


def _load_chinese_font(size: int) -> ImageFont.FreeTypeFont:
    for font_path in _FONT_CANDIDATES:
        if font_path.is_file():
            try:
                return ImageFont.truetype(
                    str(font_path), size=size,
                    index=3 if font_path.name.startswith("NotoSansCJK-") else 0,
                )
            except OSError:
                continue
    raise LabelPrinterError(
        "No Traditional Chinese font was found. On Linux Mint install "
        "fonts-noto-cjk (sudo apt install fonts-noto-cjk). "
        "On Windows install Microsoft JhengHei."
    )


def fit_header_font(
    draw: ImageDraw.ImageDraw, lines: Iterable[str], max_width: int
) -> ImageFont.FreeTypeFont:
    """Return the largest header font that fits both secondary lines."""
    lines = list(lines)
    for size in range(27, 11, -1):
        font = _load_chinese_font(size)
        boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
        if max(box[2] - box[0] for box in boxes) <= max_width:
            return font
    raise LabelPrinterError("Label header is too wide for a 50 x 30 mm label.")


def fit_body_font(
    draw: ImageDraw.ImageDraw,
    rows: list[tuple[str, str, str]],
    right_edge: int,
) -> ImageFont.FreeTypeFont:
    """Return the largest font for which all three column rows fit."""
    for size in range(46, 15, -1):
        font = _load_chinese_font(size)
        if _body_column_positions(draw, rows, font)[3] <= right_edge:
            return font
    raise LabelPrinterError("Label body is too large for a 50 x 30 mm label.")


def fit_footer_font(
    draw: ImageDraw.ImageDraw, footer: str, max_width: int
) -> ImageFont.FreeTypeFont:
    """Return the largest footer font within its requested tier."""
    for size in range(24, 15, -1):
        font = _load_chinese_font(size)
        bbox = draw.textbbox((0, 0), footer, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
    raise LabelPrinterError("Label footer is too wide for a 50 x 30 mm label.")


def _body_column_positions(
    draw: ImageDraw.ImageDraw,
    rows: list[tuple[str, str, str]],
    font: ImageFont.FreeTypeFont,
) -> tuple[int, int, int, int]:
    """Return label/value/suffix x positions and the widest rendered right edge."""
    label_x = 6
    label_width = max(draw.textbbox((0, 0), row[0], font=font)[2] for row in rows)
    value_x = label_x + label_width + 4
    value_width = max(draw.textbbox((0, 0), row[1], font=font)[2] for row in rows)
    suffix_x = value_x + value_width + 8
    widest_right = max(
        suffix_x + draw.textbbox((0, 0), row[2], font=font)[2] for row in rows
    )
    return label_x, value_x, suffix_x, widest_right


@dataclass(frozen=True)
class GrowthLabelLayout:
    """Measured fonts and spacing for one rendered growth label."""

    header_font: ImageFont.FreeTypeFont
    body_font: ImageFont.FreeTypeFont
    footer_font: ImageFont.FreeTypeFont
    header_gap: int
    section_gap: int
    body_gap: int
    footer_gap: int
    content_height: int
    label_x: int
    value_x: int
    suffix_x: int
    widest_right: int


def _text_height(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont
) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]


def _content_height(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    header_font: ImageFont.FreeTypeFont,
    body_font: ImageFont.FreeTypeFont,
    footer_font: ImageFont.FreeTypeFont,
    header_gap: int,
    section_gap: int,
    body_gap: int,
    footer_gap: int,
) -> int:
    return (
        sum(_text_height(draw, line, header_font) for line in lines[:2])
        + sum(_text_height(draw, line, body_font) for line in lines[2:5])
        + _text_height(draw, lines[5], footer_font)
        + header_gap
        + section_gap
        + body_gap * 2
        + footer_gap
    )


def _calculate_growth_label_layout(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    body_rows: list[tuple[str, str, str]],
) -> GrowthLabelLayout:
    margin_x, margin_top, margin_bottom = 6, 25, 2
    max_width = LABEL_SIZE[0] - margin_x * 2
    max_content_height = LABEL_SIZE[1] - margin_top - margin_bottom
    header_font = fit_header_font(draw, lines[:2], max_width)
    body_font = fit_body_font(draw, body_rows, LABEL_SIZE[0] - margin_x)
    footer_font = fit_footer_font(draw, lines[5], max_width)

    header_gap, section_gap, body_gap, footer_gap = 3, 16, 4, 16
    content_height = _content_height(
        draw, lines, header_font, body_font, footer_font,
        header_gap, section_gap, body_gap, footer_gap
    )
    while content_height > max_content_height and (
        header_gap > 1 or section_gap > 3 or body_gap > 2 or footer_gap > 2
    ):
        if body_gap > 2:
            body_gap -= 1
        if header_gap > 1:
            header_gap -= 1
        if section_gap > 3:
            section_gap -= 1
        if footer_gap > 2:
            footer_gap -= 1
        content_height = _content_height(
            draw, lines, header_font, body_font, footer_font,
            header_gap, section_gap, body_gap, footer_gap
        )

    while content_height > max_content_height and footer_font.size > 16:
        footer_font = _load_chinese_font(footer_font.size - 1)
        content_height = _content_height(
            draw, lines, header_font, body_font, footer_font,
            header_gap, section_gap, body_gap, footer_gap
        )

    while content_height > max_content_height and header_font.size > 12:
        header_font = _load_chinese_font(header_font.size - 1)
        content_height = _content_height(
            draw, lines, header_font, body_font, footer_font,
            header_gap, section_gap, body_gap, footer_gap
        )

    while content_height > max_content_height and body_font.size > 16:
        body_font = _load_chinese_font(body_font.size - 1)
        content_height = _content_height(
            draw, lines, header_font, body_font, footer_font,
            header_gap, section_gap, body_gap, footer_gap
        )

    if content_height > max_content_height:
        raise LabelPrinterError("Label text is too tall for a 50 x 30 mm label.")
    label_x, value_x, suffix_x, widest_right = _body_column_positions(
        draw, body_rows, body_font
    )
    header_right = margin_x + max(
        draw.textbbox((0, 0), line, font=header_font)[2] for line in lines[:2]
    )
    footer_width = draw.textbbox((0, 0), lines[5], font=footer_font)[2]
    widest_right = max(widest_right, header_right, (LABEL_SIZE[0] + footer_width) // 2)
    if widest_right > LABEL_SIZE[0] - margin_x:
        raise LabelPrinterError("A fitted label line exceeds the printable width.")
    return GrowthLabelLayout(
        header_font,
        body_font,
        footer_font,
        header_gap,
        section_gap,
        body_gap,
        footer_gap,
        content_height,
        label_x,
        value_x,
        suffix_x,
        widest_right,
    )


def growth_label_layout_metrics(
    user_data: Mapping[str, object], *, examination_date: date | None = None
) -> tuple[int, int, int, int, int, int, int, int, int, int, int, bool]:
    """Return fitted font, gap, height, and width diagnostics."""
    lines = build_growth_label_lines(user_data, examination_date=examination_date)
    body_rows = _build_growth_body_rows(user_data, parse_age(str(user_data.get("age", ""))))
    image = Image.new("1", LABEL_SIZE, color=1)
    draw = ImageDraw.Draw(image)
    layout = _calculate_growth_label_layout(draw, lines, body_rows)
    return (
        layout.header_font.size,
        layout.body_font.size,
        layout.footer_font.size,
        layout.header_gap,
        layout.section_gap,
        layout.body_gap,
        layout.footer_gap,
        layout.content_height,
        layout.label_x,
        layout.value_x,
        layout.suffix_x,
        layout.widest_right <= LABEL_SIZE[0] - 6,
    )


def render_growth_label(
    user_data: Mapping[str, object], *, examination_date: date | None = None
) -> Image.Image:
    """Render a printer-ready 384 x 240 monochrome Pillow image."""
    lines = build_growth_label_lines(user_data, examination_date=examination_date)
    age_months = parse_age(str(user_data.get("age", "")))
    body_rows = _build_growth_body_rows(user_data, age_months)
    image = Image.new("1", LABEL_SIZE, color=1)
    draw = ImageDraw.Draw(image)
    margin_x, margin_top = 6, 25
    layout = _calculate_growth_label_layout(draw, lines, body_rows)

    y = margin_top
    for index, line in enumerate(lines[:2]):
        bbox = draw.textbbox((0, 0), line, font=layout.header_font)
        draw.text((margin_x, y - bbox[1]), line, font=layout.header_font, fill=0)
        y += bbox[3] - bbox[1]
        y += layout.header_gap if index == 0 else layout.section_gap
    for index, row in enumerate(body_rows):
        row_height = max(
            _text_height(draw, part, layout.body_font) for part in row
        )
        for text, x in zip(row, (layout.label_x, layout.value_x, layout.suffix_x)):
            bbox = draw.textbbox((0, 0), text, font=layout.body_font)
            draw.text((x, y - bbox[1]), text, font=layout.body_font, fill=0)
        y += row_height
        if index < 2:
            y += layout.body_gap
    y += layout.footer_gap
    footer_bbox = draw.textbbox((0, 0), lines[5], font=layout.footer_font)
    footer_width = footer_bbox[2] - footer_bbox[0]
    footer_x = (LABEL_SIZE[0] - footer_width) // 2
    draw.text(
        (footer_x, y - footer_bbox[1]), lines[5], font=layout.footer_font, fill=0
    )
    return image


def _fit_centered_label_font(draw, text: str, max_width: int, max_size: int):
    """Return the largest Chinese-capable font that fits one label line."""
    text = str(text or "").strip()
    if not text:
        raise LabelPrinterError("Label text is missing.")
    for size in range(max_size, 7, -1):
        font = _load_chinese_font(size)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
    raise LabelPrinterError("Label text is too wide for a 50 x 30 mm label.")


def render_name_sticker(name: object) -> Image.Image:
    """Fit five spaced name rows, preferring Kai script, rotated clockwise."""
    text = str(name or "").strip()
    if not text or "\n" in text or "\r" in text:
        raise ValueError("請輸入單行姓名。")
    kai_paths = (Path("/usr/share/fonts/truetype/arphic/ukai.ttc"),
                 Path(r"C:\Windows\Fonts\kaiu.ttf"))
    font_path = next((path for path in kai_paths if path.is_file()), None)
    width, height = LABEL_SIZE[1], LABEL_SIZE[0]
    image = Image.new("1", (width, height), color=1)
    draw = ImageDraw.Draw(image)
    margin = 8
    copies, gap = 5, 16
    row_height = (height - 2 * margin - (copies - 1) * gap) / copies
    for size in range(height, 0, -1):
        font = (ImageFont.truetype(str(font_path), size=size)
                if font_path else _load_chinese_font(size))
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if text_width <= width - 2 * margin and text_height <= row_height:
            break
    else:
        raise LabelPrinterError("姓名太長，無法放入標籤。")
    for row in range(copies):
        x = (width - text_width) / 2 - bbox[0]
        y = margin + row * (row_height + gap) + (row_height - text_height) / 2 - bbox[1]
        draw.text((round(x), round(y)), text, font=font, fill=0)
    return image.transpose(Image.Transpose.ROTATE_270)


def print_name_sticker(
    name: object, *, port: str | None = None, density: int = DEFAULT_DENSITY,
    extra_feed_mm: float = 0,
) -> str:
    """Print one label containing five spaced, rotated copies of the entered name."""
    return print_image(render_name_sticker(name), port=port, density=density, extra_feed_mm=extra_feed_mm)


def render_name_birthday_label(name: object, birthday: object, patient_id: object) -> Image.Image:
    from .name_id_birthday_label import render

    return render(name, birthday, patient_id, size=LABEL_SIZE, margins=(32, 8, 8, 8),
                  font_loader=_load_chinese_font)


def print_name_birthday_label(
    user_data: Mapping[str, object], *, port: str | None = None, density: int = DEFAULT_DENSITY,
    extra_feed_mm: float = 0,
) -> str:
    """Render and print the patient name, ID, and Gregorian birthday as entered."""
    image = render_name_birthday_label(user_data.get("name"), user_data.get("birthday"), user_data.get("id"))
    return print_image(image, port=port, density=density, extra_feed_mm=extra_feed_mm)


def _code128_bar_pattern(value: str) -> str:
    """Return ReportLab's validated Code 128 bar/space pattern."""
    try:
        from reportlab.graphics.barcode.code128 import Code128
    except ImportError as exc:
        raise LabelPrinterError("Code 128 barcode support is unavailable.") from exc
    barcode = Code128(value, humanReadable=False)
    barcode._calculate()
    return barcode.decomposed


def render_name_mrn_barcode_label(name: object, mrn: object) -> Image.Image:
    """Render a centered name, MRN, and pure-raster Code 128 label."""
    name_text = str(name or "").strip()
    mrn_text = str(mrn or "").strip()
    if not name_text or not mrn_text:
        raise ValueError("Patient name and medical record number are required.")

    image = Image.new("1", LABEL_SIZE, color=1)
    draw = ImageDraw.Draw(image)
    margin = 8
    text_width = LABEL_SIZE[0] - margin * 2
    name_font = _fit_centered_label_font(draw, name_text, text_width, 62)
    mrn_font = _fit_centered_label_font(draw, mrn_text, text_width, 42)
    name_height = _text_height(draw, name_text, name_font)
    mrn_height = _text_height(draw, mrn_text, mrn_font)

    pattern = _code128_bar_pattern(mrn_text)
    modules = sum(ord(char.lower()) - ord("a") + 1 for char in pattern)
    quiet_zone = 12
    available_bar_width = LABEL_SIZE[0] - margin * 2 - quiet_zone * 2
    module_width = max(1, available_bar_width // modules)
    bar_width = modules * module_width
    barcode_height = 96
    gap = 8
    total_height = name_height + gap + mrn_height + gap + barcode_height
    if total_height > LABEL_SIZE[1] - margin * 2:
        raise ValueError("Name, MRN, and barcode do not fit on the label.")

    y = (LABEL_SIZE[1] - total_height) // 2
    for text, font in ((name_text, name_font), (mrn_text, mrn_font)):
        bbox = draw.textbbox((0, 0), text, font=font)
        x = (LABEL_SIZE[0] - (bbox[2] - bbox[0])) // 2 - bbox[0]
        draw.text((x, y - bbox[1]), text, font=font, fill=0)
        y += bbox[3] - bbox[1] + gap

    bar_x = (LABEL_SIZE[0] - bar_width) // 2
    x = bar_x
    draw_bar = True
    for symbol in pattern:
        width = (ord(symbol.lower()) - ord("a") + 1) * module_width
        if draw_bar:
            draw.rectangle((x, y, x + width - 1, y + barcode_height - 1), fill=0)
        x += width
        draw_bar = not draw_bar
    return image


def print_name_mrn_barcode_label(
    user_data: Mapping[str, object], *, port: str | None = None, density: int = DEFAULT_DENSITY,
    extra_feed_mm: float = 0,
) -> str:
    """Render and print the current patient's name, MRN, and Code 128 barcode."""
    image = render_name_mrn_barcode_label(user_data.get("name"), user_data.get("number"))
    return print_image(image, port=port, density=density, extra_feed_mm=extra_feed_mm)


def render_text_label(text, *, font_family="黑體") -> Image.Image:
    from .text_label import render_text_label as render

    font_loader = _load_chinese_font
    if font_family == "標楷體":
        paths = (Path(r"C:\Windows\Fonts\kaiu.ttf"),
                 Path(__file__).parent / "fonts" / "ukai.ttc",
                 Path("/usr/share/fonts/truetype/arphic/ukai.ttc"))
        font_path = next((path for path in paths if path.is_file()), None)
        if font_path is None:
            raise LabelPrinterError("找不到標楷體，請安裝標楷體或 AR PL UKai 字型。")
        font_loader = lambda size: ImageFont.truetype(str(font_path), size=size)
    return render(text, size=LABEL_SIZE, margins=(32, 8, 8, 8), font_loader=font_loader)


def print_text_label(text, *, port=None, density=DEFAULT_DENSITY, extra_feed_mm=0) -> str:
    return print_image(render_text_label(text), port=port, density=density, extra_feed_mm=extra_feed_mm)


def render_urine_order_label() -> Image.Image:
    from .urine_order_label import render_urine_order_label as render

    return render(size=LABEL_SIZE, margins=(8, 8, 8, 8), font_loader=_load_chinese_font)


def print_urine_order_label(*, port=None, density=DEFAULT_DENSITY, extra_feed_mm=0) -> str:
    return print_image(render_urine_order_label(), port=port, density=density, extra_feed_mm=extra_feed_mm)


def render_collection_label(name, mrn, reason) -> Image.Image:
    from .collection_label import render_collection_label as render

    return render(name, mrn, reason, size=LABEL_SIZE, margins=(8, 8, 8, 8), font_loader=_load_chinese_font)


def print_collection_label(user_data, reason, *, port=None, density=DEFAULT_DENSITY, extra_feed_mm=0) -> str:
    image = render_collection_label(user_data.get("name"), user_data.get("number"), reason)
    return print_image(image, port=port, density=density, extra_feed_mm=extra_feed_mm)


def render_mobile_barcode_label(value: object) -> Image.Image:
    from .mobile_barcode import render_mobile_barcode

    return render_mobile_barcode(value, size=LABEL_SIZE, margins=(8, 8, 8, 8), font_loader=_load_chinese_font)


def print_mobile_barcode(value: object, *, port=None, density=DEFAULT_DENSITY, extra_feed_mm=0) -> str:
    return print_image(render_mobile_barcode_label(value), port=port, density=density, extra_feed_mm=extra_feed_mm)


def render_test_pattern() -> Image.Image:
    """Render a font-independent pattern for diagnosing B1 bitmap printing."""
    image = Image.new("1", LABEL_SIZE, color=1)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, LABEL_SIZE[0] - 1, LABEL_SIZE[1] - 1), outline=0, width=3)
    for y in (30, 90, 150, 210):
        draw.rectangle((16, y, LABEL_SIZE[0] - 17, y + 7), fill=0)
    draw.line((LABEL_SIZE[0] // 2, 12, LABEL_SIZE[0] // 2, LABEL_SIZE[1] - 13), fill=0, width=3)
    return image


def _count_black_bits(chunk: bytes) -> int:
    """Count printed pixels in one packed bitmap region."""
    return sum(byte.bit_count() for byte in chunk)


class _Packet:
    def __init__(self, command: int, data: bytes):
        self.command = command
        self.data = data

    def to_bytes(self) -> bytes:
        checksum = self.command ^ len(self.data)
        for value in self.data:
            checksum ^= value
        return bytes((0x55, 0x55, self.command, len(self.data), *self.data, checksum, 0xAA, 0xAA))

    @classmethod
    def from_bytes(cls, raw: bytes) -> "_Packet":
        if raw[:2] != b"\x55\x55" or raw[-2:] != b"\xaa\xaa":
            raise PrinterCommunicationError("Printer returned a malformed packet.")
        packet = cls(raw[2], raw[4 : 4 + raw[3]])
        if packet.to_bytes() != raw:
            raise PrinterCommunicationError("Printer returned a packet with a bad checksum.")
        return packet


class _B1Client:
    def __init__(self, port: str):
        try:
            self.connection = serial.Serial(port=port, baudrate=115200, timeout=0.5)
        except (OSError, serial.SerialException) as exc:
            hint = (" On Linux Mint, check device permissions: add your user to "
                    "the dialout group, then log out and back in (see README.md)."
                    if sys.platform.startswith("linux") and
                    (isinstance(exc, PermissionError) or getattr(exc, "errno", None) == 13
                     or "Permission denied" in str(exc)) else "")
            raise PrinterCommunicationError(f"Could not open NIIMBOT on {port}: {exc}.{hint}") from exc
        self._buffer = bytearray()

    def close(self) -> None:
        self.connection.close()

    def _receive(self) -> list[_Packet]:
        self._buffer.extend(self.connection.read(1024))
        packets = []
        while len(self._buffer) > 4:
            length = self._buffer[3] + 7
            if len(self._buffer) < length:
                break
            packets.append(_Packet.from_bytes(bytes(self._buffer[:length])))
            del self._buffer[:length]
        return packets

    def _command(self, command: int, data: bytes, response_offset: int = 1) -> _Packet:
        try:
            logger.debug(
                "TX 0x%02X payload=%s",
                command,
                data.hex(" ").upper() if data else "<empty>",
            )
            self.connection.write(_Packet(command, data).to_bytes())
            for _ in range(6):
                for packet in self._receive():
                    logger.debug(
                        "RX 0x%02X payload=%s",
                        packet.command,
                        packet.data.hex(" ").upper() if packet.data else "<empty>",
                    )
                    if packet.command == command + response_offset:
                        return packet
                time.sleep(0.1)
        except (OSError, serial.SerialException) as exc:
            raise PrinterCommunicationError(f"USB communication failed: {exc}") from exc
        raise PrinterCommunicationError(f"NIIMBOT did not acknowledge command 0x{command:02X}.")

    def _expect_success(self, command: int, data: bytes, response_offset: int = 1) -> None:
        response = self._command(command, data, response_offset)
        if not response.data or not response.data[0]:
            raise PrinterCommunicationError(f"NIIMBOT rejected command 0x{command:02X}.")

    def _diagnostic_command(
        self, phase: str, command: int, data: bytes, response_command: int
    ) -> dict[str, object]:
        """Send one read-only query and retain every packet seen on the wire."""
        packet = _Packet(command, data).to_bytes()
        logger.debug(
            "B1 DIAG %s TX 0x%02X payload=%s",
            phase, command, data.hex(" ").upper() if data else "<empty>",
        )
        try:
            self.connection.write(packet)
            received: list[dict[str, object]] = []
            for _ in range(6):
                for item in self._receive():
                    raw = item.to_bytes().hex(" ").upper()
                    logger.debug(
                        "B1 DIAG %s RX 0x%02X payload=%s",
                        phase, item.command,
                        item.data.hex(" ").upper() if item.data else "<empty>",
                    )
                    received.append({
                        "command": item.command,
                        "payload": item.data.hex(" ").upper(),
                        "raw": raw,
                    })
                    if item.command == response_command:
                        return {"state": "ok", "response": received[-1], "packets": received}
                time.sleep(0.1)
        except (OSError, serial.SerialException, PrinterCommunicationError) as exc:
            return {"state": "error", "error": str(exc), "packets": []}
        return {
            "state": "no_response" if not received else "unexpected_response",
            "packets": received,
        }

    def diagnostic_read(self, phase: str) -> dict[str, object]:
        """Read printer status, heartbeat, and RFID without starting a print."""
        result: dict[str, object] = {"phase": phase, "connection": "connected", "queries": {}}
        queries = result["queries"]
        assert isinstance(queries, dict)

        heartbeat = self._diagnostic_command(phase, 0xDC, b"\x01", 0xDD)
        queries["heartbeat"] = heartbeat
        status = self._diagnostic_command(phase, 0xA3, b"\x01", 0xB3)
        queries["status"] = status
        rfid = self._diagnostic_command(phase, 0x1A, b"\x01", 0x1B)
        queries["rfid"] = rfid

        response = rfid.get("response")
        if rfid.get("state") != "ok" or not isinstance(response, dict):
            result["rfid_state"] = "no_response" if rfid.get("state") == "no_response" else "unreadable"
            return result
        try:
            data = bytes.fromhex(str(response.get("payload", "")))
            if not data or data[0] == 0:
                result["rfid_state"] = "no_rfid"
                return result
            if len(data) < 10:
                raise ValueError("RFID response is shorter than its UUID field.")
            index = 8
            barcode_length = data[index]
            index += 1
            barcode = data[index:index + barcode_length].decode(errors="replace")
            index += barcode_length
            serial_length = data[index]
            index += 1
            serial_number = data[index:index + serial_length].decode(errors="replace")
            index += serial_length
            fields: dict[str, object] = {
                "uuid": data[:8].hex().upper(),
                "barcode": barcode,
                "serial": serial_number,
            }
            if len(data) >= index + 5:
                fields["total_length"] = int.from_bytes(data[index:index + 2], "big")
                fields["used_length"] = int.from_bytes(data[index + 2:index + 4], "big")
                fields["label_type"] = data[index + 4]
            result["rfid_state"] = "read"
            result["rfid"] = fields
        except (ValueError, IndexError, UnicodeError) as exc:
            result["rfid_state"] = "unreadable"
            result["rfid_error"] = str(exc)
        return result

    @staticmethod
    def _image_packets(image: Image.Image) -> Iterable[_Packet]:
        if image.width != LABEL_SIZE[0] or not LABEL_SIZE[1] <= image.height <= 65535:
            raise ValueError(f"Invalid B1 bitmap dimensions: {image.size}.")

        # Pillow mode "1" packs pixels MSB-first. Invert so source black (0)
        # becomes a set bit (1), which is the B1 protocol's printed-pixel polarity.
        encoded = ImageOps.invert(image.convert("L")).convert("1")
        bitmap = encoded.tobytes()
        row_size = LABEL_SIZE[0] // 8
        for y in range(encoded.height):
            row = bitmap[y * row_size : (y + 1) * row_size]
            if len(row) != 48:
                raise PrinterCommunicationError(
                    f"Encoded row {y} has {len(row)} bytes; NIIMBOT B1 requires 48."
                )
            counts = tuple(
                _count_black_bits(row[start : start + 16])
                for start in (0, 16, 32)
            )
            yield _Packet(0x85, struct.pack(">H3BB", y, *counts, 1) + row)

    def print_image(self, image: Image.Image, density: int) -> None:
        self._expect_success(0x21, bytes((density,)), 16)
        self._expect_success(0x23, b"\x01", 16)
        self._expect_success(0x01, _B1_PRINT_START)
        self._expect_success(0x03, b"")
        self._expect_success(
            0x13,
            struct.pack(">HHH", image.height, image.width, _B1_PAGE_COPIES),
        )

        row_count = 0
        first_nonempty_row = None
        last_nonempty_row = None
        total_black_pixels = 0
        for packet in self._image_packets(image):
            self.connection.write(packet.to_bytes())
            row_black_pixels = sum(packet.data[2:5])
            if row_black_pixels:
                row_index = int.from_bytes(packet.data[:2], "big")
                first_nonempty_row = (
                    row_index if first_nonempty_row is None else first_nonempty_row
                )
                last_nonempty_row = row_index
                total_black_pixels += row_black_pixels
            row_count += 1
        logger.debug(
            "Bitmap summary: rows sent=%d first non-empty row=%s "
            "last non-empty row=%s total black pixels=%d",
            row_count,
            first_nonempty_row,
            last_nonempty_row,
            total_black_pixels,
        )

        self._expect_success(0xE3, b"")
        for _ in range(_B1_STATUS_POLL_LIMIT):
            status = self._command(0xA3, b"", 16)
            if len(status.data) < 4:
                raise PrinterCommunicationError(
                    "NIIMBOT returned an incomplete print-status response."
                )
            page, print_progress, feed_progress = struct.unpack(">HBB", status.data[:4])
            logger.debug(
                "Print status: page=%d print=%d%% feed=%d%%",
                page,
                print_progress,
                feed_progress,
            )
            if (
                page >= _B1_PAGE_COPIES
                and print_progress >= 100
                and feed_progress >= 100
            ):
                self._expect_success(0xF3, b"")
                return
            time.sleep(_B1_STATUS_POLL_INTERVAL)
        raise PrinterCommunicationError("NIIMBOT did not finish the print job in time.")


def print_image(
    image: Image.Image, *, port: str | None = None, density: int = DEFAULT_DENSITY,
    extra_feed_mm: float = 0,
) -> str:
    """Print one image and return the selected serial port."""
    if image.size != LABEL_SIZE:
        raise ValueError(f"Expected a {LABEL_SIZE[0]} x {LABEL_SIZE[1]} image, got {image.size}.")
    if density not in range(1, 6):
        raise ValueError("Print density must be between 1 and 5.")
    if not math.isfinite(extra_feed_mm) or extra_feed_mm < 0:
        raise ValueError("Extra feed must be a finite, nonnegative number of millimeters.")
    extra_rows = round(extra_feed_mm * 203 / 25.4)
    if image.height + extra_rows > 65535:
        raise ValueError("Extended label exceeds the B1 page height limit.")
    if extra_rows:
        extended = Image.new("1", (image.width, image.height + extra_rows), color=1)
        extended.paste(image, (0, 0))
        image = extended
    selected_port = find_niimbot_port(port)
    client = _B1Client(selected_port)
    try:
        client.print_image(image, density)
    finally:
        client.close()
    return selected_port


def read_b1_diagnostic(*, phase: str, port: str | None = None) -> dict[str, object]:
    """Read B1 status/heartbeat/RFID without sending any print command."""
    selected_port = find_niimbot_port(port)
    client = _B1Client(selected_port)
    try:
        result = client.diagnostic_read(phase)
        result["port"] = selected_port
        return result
    finally:
        client.close()


def print_growth_label(
    user_data: Mapping[str, object],
    *,
    port: str | None = None,
    density: int = DEFAULT_DENSITY,
    examination_date: date | None = None,
    extra_feed_mm: float = 0,
) -> str:
    """Render and print one growth label; return the selected serial port."""
    image = render_growth_label(user_data, examination_date=examination_date)
    return print_image(image, port=port, density=density, extra_feed_mm=extra_feed_mm)


def _sample_data(age: str = "2y6m") -> dict[str, str]:
    return {
        "age": age,
        "body_height": "92.5",
        "height_percentile": "45 百分位",
        "body_weight": "13.2",
        "weight_percentile": "50 百分位",
        "head_circumference": "49.0",
        "head_circumference_percentile": "45 百分位",
        "BMI": "15.4",
        "bmi_interpretation": "正常",
    }


def _sample_data_overeq3() -> dict[str, str]:
    return {
        "age": "5y4m",
        "body_height": "110.5",
        "height_percentile": "55 百分位",
        "body_weight": "18.3",
        "weight_percentile": "48 百分位",
        "BMI": "15.0",
        "bmi_interpretation": "正常",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate NIIMBOT B1 label previews.")
    parser.add_argument(
        "--print",
        action="store_true",
        dest="send_to_printer",
        help="send the generated image(s) to the NIIMBOT printer",
    )
    parser.add_argument("--port", help="explicit serial port, for example /dev/ttyUSB0 or COM4")
    parser.add_argument(
        "--test-pattern",
        action="store_true",
        help="render a font-independent B1 alignment pattern instead of a growth label",
    )
    parser.add_argument("--name-sticker", help="render five spaced, rotated Kai-script copies of this name")
    parser.add_argument("--preview", type=Path, help="output path for the rendered image")
    args = parser.parse_args(argv)

    if args.name_sticker is not None:
        image = render_name_sticker(args.name_sticker)
        preview_path = args.preview or Path("name_sticker_preview.jpg")
        image.convert("RGB").save(preview_path, dpi=(203, 203))
        print(f"Name sticker saved to: {preview_path.resolve()}")
        images_to_print = (image,)
    elif args.test_pattern:
        image = render_test_pattern()
        preview_path = args.preview or Path("niimbot_b1_test_pattern.png")
        image.save(preview_path)
        print(f"Test pattern saved to: {preview_path.resolve()}")
        images_to_print = (image,)
    else:
        samples = (
            ("under 3", _sample_data("2y6m"), Path("growth_label_preview_under3.png")),
            ("age 3 or older", _sample_data_overeq3(), Path("growth_label_preview_overeq3.png")),
        )
        images_to_print = []
        for description, sample, preview_path in samples:
            image = render_growth_label(sample)
            image.save(preview_path)
            images_to_print.append(image)
            (
                header_size,
                body_size,
                footer_size,
                header_gap,
                section_gap,
                body_gap,
                footer_gap,
                content_height,
                label_x,
                value_x,
                suffix_x,
                rows_fit,
            ) = growth_label_layout_metrics(sample)
            print(f"{description.capitalize()} preview:")
            print(f"  Internal age: {sample['age']}")
            print(f"  Displayed age: {format_age_for_label(sample['age'])}")
            print(f"  Header font: {header_size} px")
            print(f"  Body font: {body_size} px")
            print(f"  Footer font: {footer_size} px")
            print(f"  Header gap: {header_gap} px")
            print(f"  Section gap: {section_gap} px")
            print(f"  Body gap: {body_gap} px")
            print(f"  Footer gap: {footer_gap} px")
            print(f"  Columns: label={label_x} value={value_x} suffix={suffix_x}")
            print(f"  Total content height: {content_height} px")
            print(f"  Every row fits within 384 px: {'yes' if rows_fit else 'no'}")
            print(f"  Saved to: {preview_path.resolve()}")
    if args.send_to_printer:
        for image in images_to_print:
            selected_port = print_image(image, port=args.port)
            print(f"Printed on NIIMBOT port: {selected_port}")
    else:
        print("Preview only. Nothing was sent to the printer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
