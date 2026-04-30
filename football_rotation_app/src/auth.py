"""Authentication and coach allow-list checks."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
import tomllib

import streamlit as st

APP_DIR = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _local_app_secrets() -> dict:
    """Read app-folder secrets when Streamlit is launched from another folder."""
    secrets_path = APP_DIR / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return {}
    with secrets_path.open("rb") as file:
        return tomllib.load(file)


def _secret_value(key: str, default: object = None) -> object:
    """Read a secret value without failing when secrets are not configured."""
    try:
        value = st.secrets.get(key, None)
        if value is not None:
            return value
    except (FileNotFoundError, KeyError):
        pass
    return _local_app_secrets().get(key, default)


def _secret_section(name: str) -> dict:
    """Return a secrets section as a plain dictionary."""
    section = _secret_value(name, {})
    if hasattr(section, "to_dict"):
        return section.to_dict()
    if isinstance(section, Mapping):
        return dict(section)
    return {}


def _as_email_set(value: object) -> set[str]:
    """Convert a list or comma-separated string into lowercase emails."""
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return {str(email).strip().lower() for email in values if str(email).strip()}


def approved_coach_emails() -> set[str]:
    """Return the approved coach emails from Streamlit secrets."""
    emails = _as_email_set(_secret_value("approved_coach_emails", []))
    emails.update(_as_email_set(_secret_section("security").get("approved_coach_emails", [])))
    return emails


def _has_google_oidc_config() -> bool:
    """Check that the named Google OIDC provider has the required settings."""
    auth = _secret_section("auth")
    google = auth.get("google", {})
    if hasattr(google, "to_dict"):
        google = google.to_dict()
    if not isinstance(google, Mapping):
        google = {}

    shared_keys = ["redirect_uri", "cookie_secret"]
    provider_keys = ["client_id", "client_secret", "server_metadata_url"]
    return all(_is_configured(auth.get(key)) for key in shared_keys) and all(
        _is_configured(google.get(key)) for key in provider_keys
    )


def _is_configured(value: object) -> bool:
    """Return False for empty values and obvious example placeholders."""
    text = str(value or "").strip().lower()
    if not text:
        return False
    placeholder_markers = ["replace", "your-", "example.com"]
    return not any(marker in text for marker in placeholder_markers)


def _user_info() -> dict:
    """Return Streamlit's current user object as a normal dictionary."""
    try:
        return st.user.to_dict()
    except Exception:
        return {}


def _security_settings() -> dict:
    """Return optional security settings from Streamlit secrets."""
    return _secret_section("security")


def _allow_dev_bypass() -> bool:
    """Allow local testing only when explicitly enabled in secrets."""
    return bool(_security_settings().get("allow_dev_bypass", False))


def require_approved_coach() -> str:
    """Stop the app unless the current user is an approved coach."""
    approved_emails = approved_coach_emails()
    security = _security_settings()

    if _allow_dev_bypass():
        dev_email = str(security.get("dev_user_email", "")).strip().lower()
        if not dev_email:
            st.error("Set security.dev_user_email when using the local development bypass.")
            st.stop()
        if dev_email not in approved_emails:
            st.error("The local development email is not in approved_coach_emails.")
            st.stop()
        st.sidebar.warning("Local auth bypass is enabled.")
        return dev_email

    if not approved_emails:
        st.error("No approved coach emails are configured.")
        st.info("Add approved_coach_emails to .streamlit/secrets.toml or Streamlit Cloud secrets.")
        st.stop()

    if not _has_google_oidc_config():
        st.error("Google login is not configured.")
        st.info("Add the [auth] and [auth.google] sections to Streamlit secrets.")
        st.stop()

    user = _user_info()
    if not user.get("is_logged_in"):
        st.title("Football Rotation Manager")
        st.info("Sign in with an approved Google account to continue.")
        if st.button("Sign in with Google"):
            st.login("google")
        st.stop()

    email = str(user.get("email", "")).strip().lower()
    if not email:
        st.error("Your Google account did not provide an email address.")
        if st.button("Log out"):
            st.logout()
        st.stop()

    if user.get("email_verified") is False:
        st.error("Your Google email address is not verified.")
        if st.button("Log out"):
            st.logout()
        st.stop()

    if email not in approved_emails:
        st.error("This Google account is not approved for this app.")
        st.write(f"Signed in as: {email}")
        if st.button("Log out"):
            st.logout()
        st.stop()

    st.sidebar.caption(f"Signed in: {email}")
    if st.sidebar.button("Log out"):
        st.logout()
    return email
