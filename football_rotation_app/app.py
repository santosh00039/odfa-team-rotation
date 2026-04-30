from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from src.auth import require_approved_coach
from src.database import (
    add_player,
    complete_match_update,
    delete_player,
    get_database_label,
    get_match_details,
    get_match_players,
    get_matches,
    get_players,
    init_db,
    save_match_selection,
    update_player,
)
from src.fairness import calculate_fairness_scores, recommend_substitutes
from src.utils import (
    POSITIONS,
    PREFERRED_ROLES,
    SECONDARY_POSITIONS,
    clean_text,
    optional_text,
    player_position_text,
    role_label,
    yes_no,
)


st.set_page_config(
    page_title="Football Rotation Manager",
    layout="wide",
)


def format_player_lookup(players_df: pd.DataFrame) -> dict[int, str]:
    """Build labels for player select boxes."""
    return {
        int(row.player_id): f"{row.name} ({row.primary_position})"
        for row in players_df.itertuples()
    }


def position_index(position: str | None) -> int:
    """Return the selectbox index for a stored position."""
    return POSITIONS.index(position) if position in POSITIONS else 0


def secondary_index(position: str | None) -> int:
    """Return the selectbox index for optional secondary position."""
    return SECONDARY_POSITIONS.index(position) if position in SECONDARY_POSITIONS else 0


def display_player_table(players_df: pd.DataFrame) -> None:
    """Display players with friendly labels."""
    if players_df.empty:
        st.info("No players found.")
        return

    table = players_df.copy()
    table["positions"] = table.apply(
        lambda row: player_position_text(row["primary_position"], row["secondary_position"]),
        axis=1,
    )
    table["active"] = table["active"].apply(yes_no)
    table["last_played"] = table["last_played"].fillna("Never")

    st.dataframe(
        table[
            [
                "player_id",
                "name",
                "positions",
                "preferred_role",
                "active",
                "games_played",
                "starts",
                "subs",
                "minutes_played",
                "last_played",
                "consecutive_sitouts",
            ]
        ].rename(
            columns={
                "player_id": "ID",
                "name": "Name",
                "positions": "Positions",
                "preferred_role": "Preferred Role",
                "active": "Active",
                "games_played": "Games",
                "starts": "Starts",
                "subs": "Subs",
                "minutes_played": "Minutes",
                "last_played": "Last Played",
                "consecutive_sitouts": "Consecutive Sit-outs",
            }
        ),
        hide_index=True,
        width="stretch",
    )


def instructions_page() -> None:
    """Show coach-facing instructions for using the app."""
    st.header("Instructions")

    st.write(
        "This page explains the normal match-week process. The coach still picks the "
        "starting XI. The app helps with the bench and keeps track of rotation history."
    )

    with st.expander("Quick match-week checklist", expanded=True):
        st.markdown(
            """
            1. Open **Players** and make sure the squad list is correct.
            2. Open **Create Match** and enter the match details.
            3. Tick the players who are available.
            4. Pick exactly **11 starters**.
            5. Check the 4 recommended substitutes.
            6. Save the match selection.
            7. After the game, open **Post-Match Update** and enter minutes played.
            """
        )

    with st.expander("Players page"):
        st.markdown(
            """
            Use this page to keep your squad list up to date.

            - Add a new player when someone joins the squad.
            - Choose their main position and second position if they have one.
            - Set **Preferred role** as Starter, Rotation, or Bench. This is for your reference.
            - Set **Active** to No if a player is no longer part of the current squad.
            - Delete a player only if they were added by mistake.
            """
        )

    with st.expander("Create Match page"):
        st.markdown(
            """
            Use this page before the match.

            - Enter the match date, opponent, and venue.
            - In **Available players**, leave selected only the players who can play.
            - In **Starting XI**, choose the 11 players you want to start.
            - The app will then suggest 4 substitutes from the available players who are not starting.
            - If fewer than 15 players are available, the app will warn you that you may not have a full bench.
            """
        )

    with st.expander("How the substitute recommendation works"):
        st.markdown(
            """
            The app looks at the available players who are **not** in the starting XI.

            It gives more priority to players who:

            - have played fewer games
            - have started fewer games
            - have played fewer minutes
            - have not played recently
            - have sat out several matches in a row

            It also tries to keep the bench balanced:

            - 1 defender
            - 1 midfielder
            - 1 attacker
            - 1 extra player with the strongest rotation case
            """
        )

    with st.expander("Saving the match"):
        st.markdown(
            """
            Save the match only when you are happy with the starters and the recommended bench.

            When you save:

            - the 11 selected players are saved as starters
            - the 4 recommended players are saved as substitutes
            - available players not selected are recorded as sit-outs
            - unavailable players are recorded as unavailable

            This creates the match history and protects the record from being overwritten by the next match.
            """
        )

    with st.expander("Post-Match Update page"):
        st.markdown(
            """
            Use this page after the match is finished.

            - Select the match you just played.
            - Enter the minutes played for each starter and substitute.
            - Starters should normally have minutes greater than 0.
            - A substitute only counts as having played if their minutes are greater than 0.
            - Players who played will have their sit-out count reset.
            - Available players who did not play will have their sit-out count increased.

            Do this once per match, after the game.
            """
        )

    with st.expander("Dashboard and Match History"):
        st.markdown(
            """
            Use these pages to review the squad.

            **Dashboard** shows:

            - games played
            - starts
            - substitute appearances
            - minutes played
            - last played date
            - consecutive sit-outs
            - current rotation priority

            **Match History** shows:

            - previous match selections
            - who started
            - who was on the bench
            - who sat out
            - who was unavailable
            """
        )

    with st.expander("Sign-in and access"):
        st.markdown(
            """
            Only approved coach email addresses should be able to use the app.

            - On the hosted version, sign in with your approved Google account.
            - If your email is not approved, ask the app owner to add it.
            - On the local development version, you may see **Local auth bypass is enabled**. That is only for testing on this computer.
            """
        )


def dashboard_page() -> None:
    st.header("Dashboard")

    players = get_players(include_inactive=False)
    if players.empty:
        st.info("Add active players from the Players page.")
        return

    scored = calculate_fairness_scores(players, reference_date=date.today())
    scored["positions"] = scored.apply(
        lambda row: player_position_text(row["primary_position"], row["secondary_position"]),
        axis=1,
    )
    scored["last_played"] = scored["last_played"].fillna("Never")

    st.subheader("Active Player Rotation Status")
    st.dataframe(
        scored[
            [
                "name",
                "positions",
                "preferred_role",
                "games_played",
                "starts",
                "subs",
                "minutes_played",
                "last_played",
                "consecutive_sitouts",
                "fairness_score",
            ]
        ].rename(
            columns={
                "name": "Name",
                "positions": "Positions",
                "preferred_role": "Preferred Role",
                "games_played": "Games",
                "starts": "Starts",
                "subs": "Subs",
                "minutes_played": "Minutes",
                "last_played": "Last Played",
                "consecutive_sitouts": "Consecutive Sit-outs",
                "fairness_score": "Current Fairness Score",
            }
        ),
        hide_index=True,
        width="stretch",
    )

    chart_data = scored.sort_values("name").set_index("name")
    st.subheader("Charts")
    minutes_col, starts_col, sitouts_col = st.columns(3)

    with minutes_col:
        st.caption("Minutes by Player")
        st.bar_chart(chart_data["minutes_played"])

    with starts_col:
        st.caption("Starts by Player")
        st.bar_chart(chart_data["starts"])

    with sitouts_col:
        st.caption("Consecutive Sit-outs by Player")
        st.bar_chart(chart_data["consecutive_sitouts"])


def players_page() -> None:
    st.header("Player Management")

    st.subheader("Add New Player")
    with st.form("add_player_form", clear_on_submit=True):
        name = st.text_input("Name")
        primary_position = st.selectbox("Primary position", POSITIONS)
        secondary_position = st.selectbox("Secondary position", SECONDARY_POSITIONS)
        preferred_role = st.selectbox("Preferred role", PREFERRED_ROLES, index=1)
        active = st.checkbox("Active", value=True)
        submitted = st.form_submit_button("Add player")

    if submitted:
        clean_name = clean_text(name)
        if not clean_name:
            st.error("Player name is required.")
        else:
            ok, message = add_player(
                name=clean_name,
                primary_position=primary_position,
                secondary_position=optional_text(secondary_position),
                preferred_role=preferred_role,
                active=active,
            )
            st.success(message) if ok else st.error(message)

    players = get_players(include_inactive=True)

    st.subheader("Edit Existing Player")
    if players.empty:
        st.info("No players to edit yet.")
    else:
        labels = format_player_lookup(players)
        selected_player_id = st.selectbox(
            "Choose player to edit",
            options=list(labels.keys()),
            format_func=lambda player_id: labels[player_id],
            key="edit_player_select",
        )
        current = players[players["player_id"] == selected_player_id].iloc[0]

        with st.form("edit_player_form"):
            edit_name = st.text_input("Name", value=current["name"])
            edit_primary = st.selectbox(
                "Primary position",
                POSITIONS,
                index=position_index(current["primary_position"]),
                key="edit_primary",
            )
            edit_secondary = st.selectbox(
                "Secondary position",
                SECONDARY_POSITIONS,
                index=secondary_index(current["secondary_position"]),
                key="edit_secondary",
            )
            edit_preferred = st.selectbox(
                "Preferred role",
                PREFERRED_ROLES,
                index=PREFERRED_ROLES.index(current["preferred_role"])
                if current["preferred_role"] in PREFERRED_ROLES
                else 1,
                key="edit_preferred",
            )
            edit_active = st.checkbox("Active", value=bool(current["active"]))
            edit_submitted = st.form_submit_button("Update player")

        if edit_submitted:
            clean_name = clean_text(edit_name)
            if not clean_name:
                st.error("Player name is required.")
            else:
                ok, message = update_player(
                    player_id=selected_player_id,
                    name=clean_name,
                    primary_position=edit_primary,
                    secondary_position=optional_text(edit_secondary),
                    preferred_role=edit_preferred,
                    active=edit_active,
                )
                st.success(message) if ok else st.error(message)

    st.subheader("Delete Player")
    players_for_delete = get_players(include_inactive=True)
    if players_for_delete.empty:
        st.info("No players to delete yet.")
    else:
        delete_labels = format_player_lookup(players_for_delete)
        with st.form("delete_player_form"):
            delete_player_id = st.selectbox(
                "Choose player to delete",
                options=list(delete_labels.keys()),
                format_func=lambda player_id: delete_labels[player_id],
                key="delete_player_select",
            )
            st.warning("Deleting a player with match history will set them inactive instead.")
            delete_submitted = st.form_submit_button("Delete player")

        if delete_submitted:
            ok, message = delete_player(delete_player_id)
            st.success(message) if ok else st.error(message)

    st.subheader("All Players")
    display_player_table(get_players(include_inactive=True))


def create_match_page() -> None:
    st.header("Create Match")

    active_players = get_players(include_inactive=False)
    if active_players.empty:
        st.info("Add active players before creating a match.")
        return

    labels = format_player_lookup(active_players)
    active_ids = list(labels.keys())

    match_date = st.date_input("Match date", value=date.today())
    opponent = st.text_input("Opponent")
    venue = st.text_input("Venue")

    st.subheader("Availability")
    available_ids = st.multiselect(
        "Available players",
        options=active_ids,
        default=active_ids,
        format_func=lambda player_id: labels[player_id],
        key="match_available_players",
    )

    if len(available_ids) < 15:
        st.warning("Fewer than 15 players are available. You may not have a full bench.")

    if "match_starters" in st.session_state:
        st.session_state["match_starters"] = [
            player_id for player_id in st.session_state["match_starters"] if player_id in available_ids
        ]

    st.subheader("Starting XI")
    starter_ids = st.multiselect(
        "Select exactly 11 starters",
        options=available_ids,
        format_func=lambda player_id: labels[player_id],
        max_selections=11,
        key="match_starters",
    )

    unavailable_starters = sorted(set(starter_ids) - set(available_ids))
    valid_starters = len(starter_ids) == 11 and not unavailable_starters

    if len(starter_ids) != 11:
        st.warning(f"Select exactly 11 starters. Current selection: {len(starter_ids)}.")
    if unavailable_starters:
        st.error("All selected starters must be marked available.")

    recommendation_df = pd.DataFrame()
    substitute_ids: list[int] = []

    if valid_starters:
        candidate_players = active_players.copy()
        candidate_players["available"] = candidate_players["player_id"].isin(available_ids).astype(int)
        recommendation_df = recommend_substitutes(
            candidate_players,
            starter_ids=starter_ids,
            match_date=match_date,
            count=4,
        )

        substitute_ids = recommendation_df["player_id"].astype(int).tolist()
        eligible_sub_count = len(set(available_ids) - set(starter_ids))

        st.subheader("Recommended Substitutes")
        if eligible_sub_count >= 4 and len(substitute_ids) == 4:
            st.success("Four substitutes recommended.")
        elif eligible_sub_count < 4:
            st.warning("There are fewer than 4 available non-starters.")
        else:
            st.error("Could not recommend 4 substitutes. Check player availability.")

        if not recommendation_df.empty:
            display = recommendation_df.copy()
            display["positions"] = display.apply(
                lambda row: player_position_text(row["primary_position"], row["secondary_position"]),
                axis=1,
            )
            st.dataframe(
                display[
                    [
                        "name",
                        "positions",
                        "position_group",
                        "fairness_score",
                        "games_played",
                        "starts",
                        "minutes_played",
                        "days_since_last_played",
                        "consecutive_sitouts",
                    ]
                ].rename(
                    columns={
                        "name": "Name",
                        "positions": "Positions",
                        "position_group": "Group",
                        "fairness_score": "Fairness Score",
                        "games_played": "Games",
                        "starts": "Starts",
                        "minutes_played": "Minutes",
                        "days_since_last_played": "Days Since Last Played",
                        "consecutive_sitouts": "Consecutive Sit-outs",
                    }
                ),
                hide_index=True,
                width="stretch",
            )

    with st.form("save_match_form"):
        save_submitted = st.form_submit_button("Save Match Selection")

    if save_submitted:
        if not valid_starters:
            st.error("Fix the starting XI before saving.")
            return
        if len(set(available_ids) - set(starter_ids)) >= 4 and len(substitute_ids) != 4:
            st.error("A match with enough eligible players must have 4 substitutes.")
            return

        ok, message, match_id = save_match_selection(
            match_date=match_date,
            opponent=optional_text(opponent),
            venue=optional_text(venue),
            active_player_ids=active_ids,
            available_player_ids=available_ids,
            starter_ids=starter_ids,
            substitute_ids=substitute_ids,
        )
        if ok:
            st.success(f"{message} Use Post-Match Update after the game.")
        else:
            st.error(message)


def post_match_update_page() -> None:
    st.header("Post-Match Update")

    matches = get_matches()
    if matches.empty:
        st.info("No saved matches yet.")
        return

    match_labels = {
        int(row.match_id): (
            f"#{row.match_id} | {row.match_date} | "
            f"{row.opponent or 'No opponent'} | {row.status}"
        )
        for row in matches.itertuples()
    }
    selected_match_id = st.selectbox(
        "Select match",
        options=list(match_labels.keys()),
        format_func=lambda match_id: match_labels[match_id],
    )

    match = get_match_details(selected_match_id)
    match_players = get_match_players(selected_match_id)

    if not match:
        st.error("Match not found.")
        return

    st.write(
        f"**Match:** {match['match_date']} vs {match.get('opponent') or 'No opponent'} "
        f"at {match.get('venue') or 'No venue'}"
    )

    selected_players = match_players[match_players["role"].isin(["starter", "substitute"])].copy()
    if selected_players.empty:
        st.warning("This match has no selected starters or substitutes.")
        return

    selected_players["Role"] = selected_players["role"].apply(role_label)
    st.dataframe(
        selected_players[["name", "primary_position", "secondary_position", "Role", "minutes"]].rename(
            columns={
                "name": "Name",
                "primary_position": "Primary",
                "secondary_position": "Secondary",
                "minutes": "Saved Minutes",
            }
        ),
        hide_index=True,
        width="stretch",
    )

    if match["status"] == "completed":
        st.warning("This match is already completed. Stats are not updated again.")
        return

    st.subheader("Enter Minutes Played")
    with st.form("post_match_minutes_form"):
        minutes_by_player: dict[int, int] = {}
        for row in selected_players.itertuples():
            default_minutes = int(row.minutes or (90 if row.role == "starter" else 0))
            minutes_by_player[int(row.player_id)] = st.number_input(
                f"{row.name} ({role_label(row.role)})",
                min_value=0,
                max_value=120,
                value=default_minutes,
                step=5,
                key=f"minutes_{selected_match_id}_{row.player_id}",
            )
        submitted = st.form_submit_button("Update Player Stats")

    if submitted:
        ok, message = complete_match_update(selected_match_id, minutes_by_player)
        st.success(message) if ok else st.error(message)


def match_history_page() -> None:
    st.header("Match History")

    matches = get_matches()
    if matches.empty:
        st.info("No matches have been saved yet.")
        return

    st.dataframe(
        matches.rename(
            columns={
                "match_id": "ID",
                "match_date": "Date",
                "opponent": "Opponent",
                "venue": "Venue",
                "status": "Status",
                "starters": "Starters",
                "substitutes": "Substitutes",
                "sit_outs": "Sit-outs",
                "available_players": "Available",
            }
        ),
        hide_index=True,
        width="stretch",
    )

    labels = {
        int(row.match_id): f"#{row.match_id} | {row.match_date} | {row.opponent or 'No opponent'}"
        for row in matches.itertuples()
    }
    selected_match_id = st.selectbox(
        "View match details",
        options=list(labels.keys()),
        format_func=lambda match_id: labels[match_id],
    )

    details = get_match_players(selected_match_id)
    if details.empty:
        st.info("No player rows found for this match.")
        return

    details["Role"] = details["role"].apply(role_label)
    details["Available"] = details["available"].apply(yes_no)
    details["Positions"] = details.apply(
        lambda row: player_position_text(row["primary_position"], row["secondary_position"]),
        axis=1,
    )

    st.dataframe(
        details[["name", "Positions", "preferred_role", "Role", "Available", "minutes"]].rename(
            columns={
                "name": "Name",
                "preferred_role": "Preferred Role",
                "minutes": "Minutes",
            }
        ),
        hide_index=True,
        width="stretch",
    )


def main() -> None:
    try:
        require_approved_coach()
    except Exception as error:
        st.error("Sign-in setup failed.")
        st.info("Check Streamlit Cloud logs and confirm the Google OIDC secrets are correct.")
        st.caption(f"{type(error).__name__}: {error}")
        st.stop()

    try:
        init_db()
    except Exception as error:
        st.error("Database connection failed.")
        st.info(
            "Check the [database].url value in Streamlit Cloud secrets and confirm "
            "the Supabase database is reachable."
        )
        st.caption(f"{type(error).__name__}: {error}")
        st.stop()

    st.sidebar.title("Football Rotation")
    page = st.sidebar.radio(
        "Navigation",
        [
            "Instructions",
            "Dashboard",
            "Players",
            "Create Match",
            "Post-Match Update",
            "Match History",
        ],
    )
    st.sidebar.caption(f"Database: {get_database_label()}")

    try:
        if page == "Instructions":
            instructions_page()
        elif page == "Dashboard":
            dashboard_page()
        elif page == "Players":
            players_page()
        elif page == "Create Match":
            create_match_page()
        elif page == "Post-Match Update":
            post_match_update_page()
        elif page == "Match History":
            match_history_page()
    except Exception as error:
        st.error("Something went wrong. The details below can help with debugging.")
        st.exception(error)


if __name__ == "__main__":
    main()
