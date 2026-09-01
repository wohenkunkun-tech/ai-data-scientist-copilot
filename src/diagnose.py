from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "product_events.parquet"
DIMENSION_SETS = [
    ("country",),
    ("user_lifecycle",),
    ("platform",),
    ("country", "user_lifecycle", "platform"),
]


@dataclass
class DiagnosisResult:
    target_date: str
    baseline_start: str
    baseline_end: str
    target_rate: float
    baseline_rate: float
    delta_pp: float
    segment_diagnosis: pd.DataFrame


def _query(query: str, parameters: list[object]) -> pd.DataFrame:
    with duckdb.connect() as connection:
        return connection.execute(query, parameters).fetchdf()


def diagnose_publishing_rate(target_date: str) -> DiagnosisResult:
    target = pd.Timestamp(target_date)
    baseline_start = target - pd.Timedelta(days=7)
    baseline_end = target - pd.Timedelta(days=1)

    overall = _query(
        """
        SELECT
            event_date,
            AVG(published::INTEGER) AS publishing_rate
        FROM read_parquet(?)
        WHERE event_date BETWEEN ? AND ?
        GROUP BY event_date
        ORDER BY event_date
        """,
        [str(DATA_PATH), baseline_start, target],
    )
    baseline_rate = overall.loc[overall["event_date"] < target, "publishing_rate"].mean()
    target_rate = overall.loc[overall["event_date"] == target, "publishing_rate"].iloc[0]

    segments = []
    for dimensions in DIMENSION_SETS:
        dimension_label = " × ".join(dimensions)
        select_dimensions = ", ".join(dimensions)
        target_dimensions = ", ".join(f"target.{dimension}" for dimension in dimensions)
        group_by_dimensions = ", ".join(str(index + 1) for index in range(len(dimensions)))
        join_condition = " AND ".join(f"baseline.{dimension} = target.{dimension}" for dimension in dimensions)
        segment = _query(
            f"""
            WITH baseline AS (
                SELECT
                    {select_dimensions},
                    AVG(published::INTEGER) AS baseline_rate
                FROM read_parquet(?)
                WHERE event_date BETWEEN ? AND ?
                GROUP BY {group_by_dimensions}
            ), target AS (
                SELECT
                    {select_dimensions},
                    AVG(published::INTEGER) AS target_rate,
                    COUNT(*) AS target_users
                FROM read_parquet(?)
                WHERE event_date = ?
                GROUP BY {group_by_dimensions}
            )
            SELECT
                ? AS dimension,
                concat_ws(' | ', {target_dimensions}) AS segment,
                baseline.baseline_rate,
                target.target_rate,
                target.target_rate - baseline.baseline_rate AS delta_rate,
                target.target_users / SUM(target.target_users) OVER () AS target_user_share
            FROM baseline
            JOIN target ON {join_condition}
            """,
            [str(DATA_PATH), baseline_start, baseline_end, str(DATA_PATH), target, dimension_label],
        )
        segment["contribution_pp"] = segment["delta_rate"] * segment["target_user_share"] * 100
        segments.append(segment)

    diagnosis = pd.concat(segments, ignore_index=True).sort_values("contribution_pp")
    return DiagnosisResult(
        target_date=target.strftime("%Y-%m-%d"),
        baseline_start=baseline_start.strftime("%Y-%m-%d"),
        baseline_end=baseline_end.strftime("%Y-%m-%d"),
        target_rate=target_rate,
        baseline_rate=baseline_rate,
        delta_pp=(target_rate - baseline_rate) * 100,
        segment_diagnosis=diagnosis,
    )


if __name__ == "__main__":
    result = diagnose_publishing_rate("2026-08-31")
    print(f"Publishing rate: {result.baseline_rate:.2%} -> {result.target_rate:.2%} ({result.delta_pp:+.2f}pp)")
    print(result.segment_diagnosis.head(10).to_string(index=False))
