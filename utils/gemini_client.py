"""
gemini_client.py
------------------
Shared utility that connects to the Google Gemini API.
Every agent (Requirement Agent, Bug Analysis Agent, Evidence Agent)
calls into this single function so we don't repeat connection code 3 times.

BRING-YOUR-OWN-KEY (BYOK) MODE — how this app scales to many users for free:
Rather than the app owner's single API key being shared (and quickly
exhausted) across every visitor, each visitor pastes their OWN free Gemini
API key into the app's sidebar. That key is used ONLY for their session,
ONLY in their browser memory (st.session_state — wiped on refresh/close),
and is NEVER sent anywhere, logged, or stored on disk/server/database.

This means:
  - Each visitor's usage counts against THEIR OWN free daily quota, not
    the developer's. The app can support unlimited concurrent users for
    free, since quota scales with however many people bring a key.
  - The developer's own key (in .env / Streamlit Secrets) is now OPTIONAL
    — only used as a fallback for local development/testing if no
    session key has been entered yet, never required in production.

SECURITY NOTE:
No API key is ever hardcoded. The developer's optional fallback key is
loaded from a local .env file (excluded from GitHub via .gitignore) or
Streamlit Cloud "Secrets". A visitor's own key lives only in
st.session_state for the duration of their browser tab.
"""

import os
import time
import streamlit as st
from google import genai
from dotenv import load_dotenv

# Load variables from .env file (only works locally; harmless on cloud)
load_dotenv()

# The model we use. Gemini 2.0 Flash was retired by Google in March 2026,
# so we use Gemini 2.5 Flash instead — it's the current free-tier model,
# fast, and good enough for structured text generation like ours.
MODEL_NAME = "gemini-2.5-flash"

# Retry settings for transient errors (Google's servers being temporarily
# overloaded, or brief free-tier rate-limit hiccups). These are NOT bugs
# in our code — they're short-lived issues on Google's side that usually
# resolve within a few seconds.
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 4  # base delay; grows with each retry attempt

# Session-state key under which a visitor's own pasted API key is stored.
# Lives only in that visitor's browser session — gone on refresh/close.
SESSION_KEY_NAME = "user_gemini_api_key"


class DailyQuotaExceededError(Exception):
    """
    Raised when the active Gemini API key has hit its free-tier DAILY
    request quota (RPD) for today. This will NOT resolve by retrying in
    a few seconds — it only resolves at the next quota reset (midnight
    Pacific Time) or by using a different key.
    """
    pass


class NoApiKeyConfiguredError(Exception):
    """
    Raised when no API key is available at all — neither a visitor's
    own session key nor a developer fallback key. The UI should prompt
    the visitor to paste their own free Gemini API key.
    """
    pass


def _streamlit_secrets_file_exists() -> bool:
    """
    Checks whether a Streamlit secrets.toml file actually exists, WITHOUT
    ever touching st.secrets directly. Simply accessing st.secrets (even
    inside try/except) makes Streamlit print its own "No secrets found"
    warning to the app UI when no file exists. Checking the file's
    existence ourselves first avoids ever triggering that warning when
    there's nothing to find (e.g. running locally without Cloud Secrets).
    """
    import pathlib

    candidate_paths = [
        pathlib.Path.cwd() / ".streamlit" / "secrets.toml",
        pathlib.Path.home() / ".streamlit" / "secrets.toml",
    ]
    return any(p.exists() for p in candidate_paths)


def get_user_session_key() -> str | None:
    """Returns the visitor's own pasted API key for this session, if set."""
    return st.session_state.get(SESSION_KEY_NAME) or None


def set_user_session_key(api_key: str) -> None:
    """Stores the visitor's own API key in session memory for this tab only."""
    st.session_state[SESSION_KEY_NAME] = api_key.strip()


def clear_user_session_key() -> None:
    """Removes the visitor's own API key from session memory."""
    st.session_state[SESSION_KEY_NAME] = ""


def _get_developer_fallback_keys() -> list[str]:
    """
    Fetches the developer's OPTIONAL fallback key(s), used only if a
    visitor hasn't entered their own key yet (mainly useful for the
    developer's own local testing). Supports a comma-separated list for
    multi-key rotation, same as before.
    """
    raw_value = None

    if _streamlit_secrets_file_exists():
        try:
            if "GEMINI_API_KEY" in st.secrets:
                raw_value = st.secrets["GEMINI_API_KEY"]
        except Exception:
            pass

    if not raw_value:
        raw_value = os.getenv("GEMINI_API_KEY")

    if not raw_value:
        return []

    return [k.strip() for k in raw_value.split(",") if k.strip()]


def get_active_keys() -> list[str]:
    """
    Determines which key(s) to actually use for this request, in order:
      1. The visitor's own session key, if they've entered one (BYOK mode
         — this is the expected path once deployed for real users)
      2. The developer's optional fallback key(s) from .env/Secrets
         (useful for the developer's own local testing without having
         to paste a key into the UI every time)

    Raises NoApiKeyConfiguredError if neither is available, so the UI can
    prompt the visitor to paste their own free key.
    """
    user_key = get_user_session_key()
    if user_key:
        return [user_key]

    fallback_keys = _get_developer_fallback_keys()
    if fallback_keys:
        return fallback_keys

    raise NoApiKeyConfiguredError(
        "No Gemini API key is set for this session. Please paste your own "
        "free Gemini API key in the sidebar to use QA Copilot."
    )


def get_client_for_key(api_key: str) -> genai.Client:
    """Creates a Gemini API client for a specific key."""
    return genai.Client(api_key=api_key)


def ask_gemini(prompt: str) -> str:
    """
    Sends a text-only prompt to Gemini and returns the plain text response.
    This is the function used by the text-only agents (Requirement, Bug
    Analysis, Evidence, Orchestrator).

    Uses the active key (visitor's own session key, or developer fallback)
    and automatically retries on transient errors.
    """
    return _generate_with_key_rotation(contents=prompt)


def ask_gemini_with_image(prompt: str, image_bytes: bytes, mime_type: str) -> str:
    """
    Sends a prompt PLUS an image to Gemini and returns the plain text
    response. Used by the Evidence Agent's screenshot-analysis feature,
    where Gemini actually looks at a screenshot the tester uploaded and
    points out visible errors, rather than just suggesting what to collect.

    image_bytes: raw bytes of the uploaded image (e.g. from Streamlit's
                 file_uploader, via uploaded_file.getvalue())
    mime_type:   e.g. 'image/png' or 'image/jpeg'

    Has the same automatic retry + key behavior as ask_gemini().
    """
    from google.genai import types

    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    contents = [prompt, image_part]
    return _generate_with_key_rotation(contents=contents)


def _generate_with_key_rotation(contents):
    """
    Tries the active key(s) in order (visitor's own key first if set,
    otherwise the developer's fallback key list). If a key hits its daily
    quota, automatically rotates to the next available key (if any) —
    this mainly matters when the developer has configured multiple
    fallback keys for their own testing; a visitor's single session key
    has nothing to rotate to, so it will surface DailyQuotaExceededError
    directly if exhausted.
    """
    keys = get_active_keys()
    last_quota_error = None

    for key_index, active_key in enumerate(keys):
        client = get_client_for_key(active_key)
        try:
            return _generate_with_retry(client, contents=contents)
        except DailyQuotaExceededError as e:
            last_quota_error = e
            continue  # try the next key, if any

    # Every available key has been confirmed exhausted for today.
    raise DailyQuotaExceededError(
        "Today's free Gemini quota has been used up for the configured "
        "key(s). This resets at midnight Pacific Time (roughly 12:30 PM "
        "IST). If you're using your own key, you can also generate a new "
        "free key from a different Google account for a separate quota."
    ) from last_quota_error


def _generate_with_retry(client: genai.Client, contents):
    """
    Retry wrapper for a SINGLE API key/client.

    Distinguishes between two kinds of errors:
      - Daily quota exhausted (RPD limit hit on THIS key): not worth
        retrying on this same key, since it only resets at midnight
        Pacific Time. Raises DailyQuotaExceededError so the caller can
        try a different key, if any.
      - Transient errors (503 server overload, brief per-minute 429):
        worth a short retry with backoff, since these usually clear
        within seconds.
    """
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=contents,
            )
            return response.text
        except Exception as e:
            error_text = str(e)

            # Invalid/malformed key — surface this clearly so the UI can
            # tell the visitor their pasted key isn't valid, rather than
            # treating it as a generic failure.
            if "API_KEY_INVALID" in error_text or "API key not valid" in error_text:
                raise ValueError(
                    "That API key doesn't look valid. Please double-check "
                    "it was copied correctly from Google AI Studio."
                ) from e

            # Daily quota exhausted — this specific quotaId tells us it's
            # the requests-PER-DAY limit, not a short-lived rate limit.
            if "PerDay" in error_text or "RPD" in error_text:
                raise DailyQuotaExceededError(
                    "This API key has used up today's free Gemini "
                    "requests."
                ) from e

            is_transient = "503" in error_text or "UNAVAILABLE" in error_text or "429" in error_text
            last_error = e

            if is_transient and attempt < MAX_RETRIES:
                wait_time = RETRY_DELAY_SECONDS * attempt  # 4s, then 8s, then 12s
                time.sleep(wait_time)
                continue
            else:
                raise last_error

    # Should never reach here, but just in case:
    raise last_error
