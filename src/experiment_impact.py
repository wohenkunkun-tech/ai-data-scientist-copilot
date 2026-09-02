from math import erf, sqrt
from pathlib import Path

import duckdb
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
EVENTS_PATH = DATA_DIR / "product_events.parquet"
EXPOSURES_PATH = DATA_DIR / "experiment_exposures.parquet"
EXPERIMENTS_PATH = DATA_DIR / "experiments.parquet"


def query_experiment_impact(target_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    target = pd.Timestamp(target_date)
    with duckdb.connect() as connection:
        rollouts = connection.execute(
            """
            SELECT experiment_name, targeting, traffic_share, start_date
            FROM read_parquet(?)
            WHERE experiment_type = 'full_rollout' AND start_date <= ?
              AND (end_date IS NULL OR end_date >= ?)
            """,
            [str(EXPERIMENTS_PATH), target, target],
        ).fetchdf()
        ab_experiments = connection.execute(
            """
            SELECT experiment_id, experiment_name, traffic_share
            FROM read_parquet(?)
            WHERE experiment_type = 'ab_test' AND start_date <= ? AND end_date >= ?
            """,
            [str(EXPERIMENTS_PATH), target, target],
        ).fetchdf()

        results = []
        for experiment in ab_experiments.itertuples(index=False):
            metrics = connection.execute(
                """
                SELECT exposure.variant, COUNT(*) AS users, AVG(event.published::INTEGER) AS publishing_rate
                FROM read_parquet(?) AS exposure
                JOIN read_parquet(?) AS event
                  ON exposure.event_date = event.event_date AND exposure.user_id = event.user_id
                WHERE exposure.experiment_id = ? AND exposure.event_date = ?
                GROUP BY 1
                """,
                [str(EXPOSURES_PATH), str(EVENTS_PATH), experiment.experiment_id, target],
            ).fetchdf().set_index("variant")
            if {"control", "treatment"}.issubset(metrics.index):
                control = metrics.loc["control"]
                treatment = metrics.loc["treatment"]
                difference = treatment.publishing_rate - control.publishing_rate
                standard_error = sqrt(
                    control.publishing_rate * (1 - control.publishing_rate) / control.users
                    + treatment.publishing_rate * (1 - treatment.publishing_rate) / treatment.users
                )
                z_score = difference / standard_error if standard_error else 0
                p_value = 2 * (1 - 0.5 * (1 + erf(abs(z_score) / sqrt(2))))
                results.append({
                    "experiment_name": experiment.experiment_name,
                    "traffic_share": experiment.traffic_share,
                    "control_users": int(control.users),
                    "treatment_users": int(treatment.users),
                    "control_rate": control.publishing_rate,
                    "treatment_rate": treatment.publishing_rate,
                    "lift_pp": difference * 100,
                    "p_value": p_value,
                    "verdict": "可能影响核心指标" if p_value < 0.05 and difference < 0 else "未发现显著负向影响",
                })
    return rollouts, pd.DataFrame(results)
