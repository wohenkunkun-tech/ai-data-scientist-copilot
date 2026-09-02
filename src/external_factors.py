from datetime import date

import holidays
import pandas as pd

COUNTRY_CALENDARS = {
    "US": holidays.US,
    "BR": holidays.BR,
    "JP": holidays.JP,
    "GB": holidays.GB,
    "DE": holidays.DE,
}


def school_breaks(country: str, target_date: date) -> list[str]:
    month = target_date.month
    day = target_date.day
    if country == "US":
        if (month == 6 and day >= 15) or month in {7, 8}:
            return ["美国 K-12 暑假窗口（近似：6月中旬至8月）"]
        if month == 12 and day >= 20 or (month == 1 and day <= 5):
            return ["美国 K-12 寒假窗口（近似：12月下旬至1月初）"]
    if country in {"GB", "DE"} and month in {7, 8}:
        return ["欧洲暑假窗口（近似：7月至8月）"]
    if country == "JP" and month in {7, 8}:
        return ["日本暑假窗口（近似：7月下旬至8月）"]
    if country == "BR" and month in {12, 1, 2}:
        return ["巴西暑假窗口（近似：12月至2月）"]
    return []


def external_calendar_context(target_date: str, countries: list[str]) -> pd.DataFrame:
    parsed_date = pd.Timestamp(target_date).date()
    records = []
    for country in countries:
        holiday_name = COUNTRY_CALENDARS[country](years=[parsed_date.year]).get(parsed_date)
        factors = []
        if holiday_name:
            factors.append(f"法定节假日：{holiday_name}")
        factors.extend(school_breaks(country, parsed_date))
        records.append(
            {
                "country": country,
                "date": parsed_date.isoformat(),
                "external_factors": "；".join(factors) if factors else "未识别到节假日或预定义学期窗口",
                "needs_local_calendar": "是" if factors and "近似" in "；".join(factors) else "否",
            }
        )
    return pd.DataFrame(records)
