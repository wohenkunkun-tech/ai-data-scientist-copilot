from pathlib import Path

import numpy as np
import pandas as pd

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "product_events.parquet"
RNG = np.random.default_rng(20260901)

COUNTRIES = ["US", "BR", "JP", "GB", "DE"]
COUNTRY_WEIGHTS = [0.34, 0.24, 0.16, 0.14, 0.12]
PLATFORMS = ["Android", "iOS", "Web"]
PLATFORM_WEIGHTS = [0.52, 0.36, 0.12]
LIFECYCLES = ["new", "existing"]
LIFECYCLE_WEIGHTS = [0.42, 0.58]
BASE_RATES = {
    "US": 0.052,
    "BR": 0.046,
    "JP": 0.041,
    "GB": 0.049,
    "DE": 0.044,
}


def publishing_rate(country: str, platform: str, lifecycle: str, date: pd.Timestamp) -> float:
    rate = BASE_RATES[country]
    rate += {"Android": -0.002, "iOS": 0.002, "Web": 0.000}[platform]
    rate += {"new": -0.004, "existing": 0.001}[lifecycle]

    if date == pd.Timestamp("2026-08-31") and country == "US" and platform == "Android" and lifecycle == "new":
        rate -= 0.032

    return rate


def main() -> None:
    dates = pd.date_range("2026-08-01", "2026-08-31", freq="D")
    records = []
    user_id = 1

    for date in dates:
        daily_users = 18_000
        countries = RNG.choice(COUNTRIES, size=daily_users, p=COUNTRY_WEIGHTS)
        platforms = RNG.choice(PLATFORMS, size=daily_users, p=PLATFORM_WEIGHTS)
        lifecycles = RNG.choice(LIFECYCLES, size=daily_users, p=LIFECYCLE_WEIGHTS)

        for country, platform, lifecycle in zip(countries, platforms, lifecycles, strict=True):
            published = RNG.random() < publishing_rate(country, platform, lifecycle, date)
            records.append(
                {
                    "event_date": date,
                    "user_id": user_id,
                    "country": country,
                    "platform": platform,
                    "user_lifecycle": lifecycle,
                    "published": published,
                }
            )
            user_id += 1

    events = pd.DataFrame(records)
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    events.to_parquet(OUTPUT_PATH, index=False)
    print(f"Wrote {len(events):,} events to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
