import base64
import binascii
import os
from pathlib import Path

CAPTURE_ARTIFACT_DIRECTORY = "CAPTURE_ARTIFACT_DIRECTORY"
CAPTURE_AUTH_PROFILE_KEY = "CAPTURE_AUTH_PROFILE_KEY"
CAPTURE_AWS_ACCESS_KEY_ID = "CAPTURE_AWS_ACCESS_KEY_ID"
CAPTURE_AWS_REGION = "CAPTURE_AWS_REGION"
CAPTURE_AWS_SECRET_ACCESS_KEY = "CAPTURE_AWS_SECRET_ACCESS_KEY"
CAPTURE_BROWSER_SLOT_COUNT = "CAPTURE_BROWSER_SLOT_COUNT"
CAPTURE_CONTRACTS_DIR = "CAPTURE_CONTRACTS_DIR"
CAPTURE_DYNAMODB_ENDPOINT_URL = "CAPTURE_DYNAMODB_ENDPOINT_URL"
CAPTURE_LEASE_DURATION_SECONDS = "CAPTURE_LEASE_DURATION_SECONDS"
CAPTURE_LOGIN_DISPLAY_START = "CAPTURE_LOGIN_DISPLAY_START"
CAPTURE_LOGIN_MAX_SESSIONS = "CAPTURE_LOGIN_MAX_SESSIONS"
CAPTURE_LOGIN_NOVNC_ROOT = "CAPTURE_LOGIN_NOVNC_ROOT"
CAPTURE_LOGIN_PORT = "CAPTURE_LOGIN_PORT"
CAPTURE_LOGIN_VNC_PORT_START = "CAPTURE_LOGIN_VNC_PORT_START"
CAPTURE_LOGIN_WEBSOCKIFY_PORT_START = "CAPTURE_LOGIN_WEBSOCKIFY_PORT_START"
CAPTURE_OUTBOX_LEASE_SECONDS = "CAPTURE_OUTBOX_LEASE_SECONDS"
CAPTURE_OUTBOX_POLL_SECONDS = "CAPTURE_OUTBOX_POLL_SECONDS"
CAPTURE_OUTBOX_RETRY_SECONDS = "CAPTURE_OUTBOX_RETRY_SECONDS"
CAPTURE_RABBITMQ_URL = "CAPTURE_RABBITMQ_URL"
CAPTURE_S3_ENDPOINT_URL = "CAPTURE_S3_ENDPOINT_URL"
CAPTURE_SESSION_TTL_SECONDS = "CAPTURE_SESSION_TTL_SECONDS"


def required(name: str) -> str:
    value = os.getenv(name)

    if value is None or not value.strip():
        raise ValueError(f"{name} is required")

    return value


def required_int(name: str) -> int:
    value = os.getenv(name)

    if value is None or not value.strip():
        raise ValueError(f"{name} is required")

    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


def positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))

    if value < 1:
        raise ValueError(f"{name} must be positive")

    return value


def positive_float(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))

    if value <= 0:
        raise ValueError(f"{name} must be positive")

    return value


def a_path(name: str, default: str) -> Path:
    value = os.getenv(name, default)

    if not value.strip():
        raise ValueError(f"{name} must be non-empty")

    return Path(value)


def auth_profile_key() -> bytes:
    value = required(CAPTURE_AUTH_PROFILE_KEY)

    try:
        key = base64.b64decode(value, validate=True)
    except binascii.Error as error:
        raise ValueError(f"{CAPTURE_AUTH_PROFILE_KEY} must be base64") from error

    if len(key) != 32:
        raise ValueError(f"{CAPTURE_AUTH_PROFILE_KEY} must decode to 32 bytes")

    return key
