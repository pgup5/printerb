"""集中處理生長曲線、BMI、百分位與年齡代碼等純計算。"""

from __future__ import annotations

import re

try:
    from .taiwandata import BOY_BMI_DATA, GIRL_BMI_DATA, PERCENTILES
except ImportError:
    PERCENTILES, BOY_BMI_DATA, GIRL_BMI_DATA = [], [], []


def interpolate_value(x, x1, x2, y1, y2):
    if abs(x2 - x1) < 1e-9:
        return y1
    return y1 + (y2 - y1) * ((x - x1) / (x2 - x1))


def get_percentiles_for_age(age_years, data_table, percentiles=None):
    """Return all percentile cutoff values for an age."""
    if not data_table:
        return {}
    percentiles = PERCENTILES if percentiles is None else percentiles
    if age_years <= data_table[0][0]:
        return dict(zip(percentiles, data_table[0][1:]))
    if age_years >= data_table[-1][0]:
        return dict(zip(percentiles, data_table[-1][1:]))

    for index in range(len(data_table) - 1):
        age1, row1 = data_table[index][0], data_table[index][1:]
        age2, row2 = data_table[index + 1][0], data_table[index + 1][1:]
        if age1 <= age_years <= age2:
            interpolated_row = [
                interpolate_value(age_years, age1, age2, value1, value2)
                for value1, value2 in zip(row1, row2)
            ]
            return dict(zip(percentiles, interpolated_row))
    return {}


def get_percentile_for_value(age_years, value, data_table, percentiles=None):
    """Calculate the percentile position for a height or weight value."""
    cutoffs = get_percentiles_for_age(age_years, data_table, percentiles)
    if not cutoffs:
        return 0.0

    sorted_percentiles = sorted(cutoffs.keys())
    if value < cutoffs[sorted_percentiles[0]]:
        return float(sorted_percentiles[0])
    if value > cutoffs[sorted_percentiles[-1]]:
        return float(sorted_percentiles[-1])

    for index in range(len(sorted_percentiles) - 1):
        low_percentile = sorted_percentiles[index]
        high_percentile = sorted_percentiles[index + 1]
        low_value = cutoffs[low_percentile]
        high_value = cutoffs[high_percentile]
        if low_value <= value <= high_value:
            return interpolate_value(
                value,
                low_value,
                high_value,
                float(low_percentile),
                float(high_percentile),
            )
    return float(sorted_percentiles[-1])


def compute_bmi(weight_kg, height_cm):
    """Calculate BMI using kilograms and centimeters."""
    if height_cm <= 0:
        return 0
    height_m = height_cm / 100.0
    return weight_kg / (height_m ** 2)


def _validate_gestational_age(gestational_age_weeks):
    ga = float(gestational_age_weeks)
    if not 0 < ga <= 40:
        raise ValueError("GA must be greater than 0 and no more than 40 weeks")
    return ga


def calculate_corrected_age(age_years, gestational_age_weeks):
    """Subtract prematurity correction, without returning a negative age."""
    ga = _validate_gestational_age(gestational_age_weeks)
    return max(0.0, age_years - ((40 - ga) / 52.0))


def get_growth_percentile_age(chronological_age, gestational_age_weeks=None):
    """Select the age used by growth percentiles; correction ends at age two."""
    if gestational_age_weeks in (None, ""):
        return chronological_age

    ga = _validate_gestational_age(gestational_age_weeks)
    if chronological_age < 2.0:
        return calculate_corrected_age(chronological_age, ga)
    return chronological_age


def interpret_bmi(gender, age_years, bmi):
    """Classify BMI using the existing age- and gender-specific cutoffs."""
    reference_data = BOY_BMI_DATA if gender == "boy" else GIRL_BMI_DATA
    if not reference_data:
        return "N/A"

    if age_years <= reference_data[0][0]:
        cutoffs = reference_data[0]
    elif age_years >= reference_data[-1][0]:
        cutoffs = reference_data[-1]
    else:
        for index in range(len(reference_data) - 1):
            age1, age2 = reference_data[index][0], reference_data[index + 1][0]
            if age1 <= age_years <= age2:
                underweight = interpolate_value(
                    age_years, age1, age2,
                    reference_data[index][1], reference_data[index + 1][1],
                )
                overweight = interpolate_value(
                    age_years, age1, age2,
                    reference_data[index][2], reference_data[index + 1][2],
                )
                obese = interpolate_value(
                    age_years, age1, age2,
                    reference_data[index][3], reference_data[index + 1][3],
                )
                cutoffs = [None, underweight, overweight, obese]
                break

    underweight, overweight, obese = cutoffs[1], cutoffs[2], cutoffs[3]
    if bmi < underweight:
        return "過輕"
    if bmi < overweight:
        return "正常"
    if bmi < obese:
        return "過重"
    return "肥胖"


def format_percentile_display(percentile):
    """Format a percentile using Traditional Chinese display wording."""
    rounded_percentile = round(percentile)
    if percentile < 3:
        return "<第3百分位"
    if percentile > 97:
        return ">第97百分位"
    return f"第{rounded_percentile}百分位"


def parse_age_for_codes(age_str):
    """Convert an XyYm age string to total months."""
    if not isinstance(age_str, str):
        return None
    match = re.match(r"^(\d+)y(\d+)m$", age_str.strip())
    if match:
        years, months = (int(value) for value in match.groups())
        if months < 12:
            return years * 12 + months
    return None


def get_age_dependent_input_states(age_str):
    """Return whether head-circumference and GA inputs should be enabled."""
    age_months = parse_age_for_codes(age_str)
    if age_months is None:
        return True, True
    return age_months < 36, age_months < 24


def get_education_code(user_data):
    """Return the existing age-based education T-code."""
    total_months = parse_age_for_codes(user_data.get("age", ""))
    if total_months is None:
        return None
    boundaries = (
        (2, "T1"), (4, "T2"), (6, "T3"), (12, "T4"),
        (18, "T5"), (24, "T6"), (36, "T7"), (60, "T8"), (84, "T9"),
    )
    return next((code for maximum, code in boundaries if total_months < maximum), None)


def get_screen_code(user_data):
    """Return the existing age-based screening S-code."""
    total_months = parse_age_for_codes(user_data.get("age", ""))
    if total_months is None:
        return None
    if total_months < 6:
        return "N/A"
    boundaries = (
        (9, "S1"), (12, "S2"), (15, "S3"), (18, "S4"),
        (24, "S5"), (36, "S6"), (48, "S7"), (60, "S8"), (84, "S9"),
    )
    return next((code for maximum, code in boundaries if total_months < maximum), None)
