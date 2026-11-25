import base64
import binascii
import os

AUTH_PROFILE_KEY_ENVIRONMENT = "CAPTURE_AUTH_PROFILE_KEY"


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


def auth_profile_key() -> bytes:
    value = required(AUTH_PROFILE_KEY_ENVIRONMENT)

    try:
        key = base64.b64decode(value, validate=True)
    except binascii.Error as error:
        raise ValueError(f"{AUTH_PROFILE_KEY_ENVIRONMENT} must be base64") from error

    if len(key) != 32:
        raise ValueError(f"{AUTH_PROFILE_KEY_ENVIRONMENT} must decode to 32 bytes")

    return key
