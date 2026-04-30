"""Fairness scoring and substitute recommendation logic."""

from __future__ import annotations

from datetime import date
from typing import Iterable

import pandas as pd

DEFENDER_POSITIONS = {
    "GOALKEEPER",
    "CENTRE BACK",
    "LEFT BACK",
    "RIGHT BACK",
    "LEFT WING BACK",
    "RIGHT WING BACK",
}
MIDFIELDER_POSITIONS = {
    "DEFENSIVE MIDFIELDER",
    "CENTRAL MIDFIELDER",
    "ATTACKING MIDFIELDER",
    "LEFT MIDFIELDER",
    "RIGHT MIDFIELDER",
}
ATTACKER_POSITIONS = {
    "LEFT WINGER",
    "RIGHT WINGER",
    "STRIKER",
    "CENTRE FORWARD",
}

POSITION_GROUPS = {
    "Defender": DEFENDER_POSITIONS,
    "Midfielder": MIDFIELDER_POSITIONS,
    "Attacker": ATTACKER_POSITIONS,
}

REQUIRED_SUB_GROUPS = ["Defender", "Midfielder", "Attacker"]


def position_group_for_player(primary_position: str, secondary_position: str | None = None) -> str:
    """Map a player position to the simple group used for substitute balance."""
    positions = [primary_position, secondary_position]
    for position in positions:
        if not position:
            continue
        clean_position = str(position).upper()
        for group_name, group_positions in POSITION_GROUPS.items():
            if clean_position in group_positions:
                return group_name
    return "Other"


def calculate_fairness_scores(
    players_df: pd.DataFrame,
    reference_date: date | str | None = None,
) -> pd.DataFrame:
    """Add fairness score columns to a player dataframe.

    Higher scores mean a player should have higher rotation priority.
    Missing last_played dates are treated as high priority.
    """
    df = players_df.copy()
    if df.empty:
        df["days_since_last_played"] = []
        df["fairness_score"] = []
        return df

    numeric_columns = ["games_played", "starts", "minutes_played", "consecutive_sitouts"]
    for column in numeric_columns:
        if column not in df.columns:
            df[column] = 0
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)

    max_games_played = df["games_played"].max()
    max_starts = df["starts"].max()
    max_minutes = df["minutes_played"].max()

    reference = pd.to_datetime(reference_date or date.today()).normalize()
    last_played = pd.to_datetime(df.get("last_played"), errors="coerce")
    days_since = (reference - last_played).dt.days

    known_days = days_since.dropna()
    missing_priority_days = 365
    if not known_days.empty:
        missing_priority_days = max(int(known_days.max()) + 30, missing_priority_days)

    df["days_since_last_played"] = days_since.fillna(missing_priority_days).clip(lower=0)

    df["fairness_score"] = (
        (max_games_played - df["games_played"]) * 3
        + (max_starts - df["starts"]) * 2
        + (max_minutes - df["minutes_played"]) * 0.02
        + df["days_since_last_played"] * 0.2
        + df["consecutive_sitouts"] * 4
    )

    df["fairness_score"] = df["fairness_score"].round(2)
    return df


def recommend_substitutes(
    players_df: pd.DataFrame,
    starter_ids: Iterable[int],
    match_date: date | str | None = None,
    count: int = 4,
) -> pd.DataFrame:
    """Recommend substitutes from active, available non-starters.

    The function first tries to select one defender, one midfielder, and one
    attacker. Any remaining substitute spots are filled by fairness score.
    """
    starter_id_set = {int(player_id) for player_id in starter_ids}
    eligible = players_df.copy()

    if eligible.empty:
        return eligible

    if "active" in eligible.columns:
        eligible = eligible[eligible["active"].astype(bool)]
    if "available" in eligible.columns:
        eligible = eligible[eligible["available"].astype(bool)]

    eligible = eligible[~eligible["player_id"].astype(int).isin(starter_id_set)]
    if eligible.empty:
        return eligible

    eligible["position_group"] = eligible.apply(
        lambda row: position_group_for_player(
            row.get("primary_position"),
            row.get("secondary_position"),
        ),
        axis=1,
    )
    eligible = calculate_fairness_scores(eligible, reference_date=match_date)
    eligible = eligible.sort_values(
        by=["fairness_score", "consecutive_sitouts", "minutes_played", "name"],
        ascending=[False, False, True, True],
    )

    selected_ids: list[int] = []

    for group_name in REQUIRED_SUB_GROUPS:
        if len(selected_ids) >= count:
            break
        group_pool = eligible[
            (eligible["position_group"] == group_name)
            & (~eligible["player_id"].astype(int).isin(selected_ids))
        ]
        if not group_pool.empty:
            selected_ids.append(int(group_pool.iloc[0]["player_id"]))

    remaining_pool = eligible[~eligible["player_id"].astype(int).isin(selected_ids)]
    for _, row in remaining_pool.iterrows():
        if len(selected_ids) >= count:
            break
        selected_ids.append(int(row["player_id"]))

    recommended = eligible[eligible["player_id"].astype(int).isin(selected_ids)].copy()
    return recommended.sort_values(
        by=["fairness_score", "consecutive_sitouts", "minutes_played", "name"],
        ascending=[False, False, True, True],
    ).head(count)
