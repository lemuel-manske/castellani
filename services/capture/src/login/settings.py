import base64
import binascii
import os
import uuid
from dataclasses import dataclass, field

from environment import positive_int, required, required_int

AUTH_PROFILE_KEY_ENVIRONMENT = "CAPTURE_AUTH_PROFILE_KEY"

DEFAULT_SESSION_TTL_SECONDS = 1800
DEFAULT_LOGIN_MAX_SESSIONS = 4
DEFAULT_LOGIN_DISPLAY_START = 100
DEFAULT_LOGIN_VNC_PORT_START = 5900
DEFAULT_LOGIN_WEBSOCKIFY_PORT_START = 6080
DEFAULT_LOGIN_NOVNC_DIRECTORY = "/usr/share/novnc"


@dataclass(frozen=True)
class LoginSettings:
    """Runtime configuration for the dedicated interactive-login manager."""

    port: int

    aws_region: str
    aws_access_key_id: str
    aws_secret_access_key: str

    dynamodb_endpoint_url: str
    s3_endpoint_url: str

    auth_profile_key: bytes

    session_ttl_seconds: int
    max_sessions: int

    display_start: int
    vnc_port_start: int
    websockify_port_start: int
    novnc_root: str
    manager_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @classmethod
    def from_environment(cls) -> "LoginSettings":
        return cls(
            port=required_int("CAPTURE_LOGIN_PORT"),
            aws_region=required("CAPTURE_AWS_REGION"),
            aws_access_key_id=required("CAPTURE_AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=required("CAPTURE_AWS_SECRET_ACCESS_KEY"),
            dynamodb_endpoint_url=required("CAPTURE_DYNAMODB_ENDPOINT_URL"),
            s3_endpoint_url=required("CAPTURE_S3_ENDPOINT_URL"),
            auth_profile_key=auth_profile_key(),
            session_ttl_seconds=positive_int(
                "CAPTURE_SESSION_TTL_SECONDS",
                DEFAULT_SESSION_TTL_SECONDS,
            ),
            max_sessions=positive_int(
                "CAPTURE_LOGIN_MAX_SESSIONS",
                DEFAULT_LOGIN_MAX_SESSIONS,
            ),
            display_start=positive_int(
                "CAPTURE_LOGIN_DISPLAY_START",
                DEFAULT_LOGIN_DISPLAY_START,
            ),
            vnc_port_start=positive_int(
                "CAPTURE_LOGIN_VNC_PORT_START",
                DEFAULT_LOGIN_VNC_PORT_START,
            ),
            websockify_port_start=positive_int(
                "CAPTURE_LOGIN_WEBSOCKIFY_PORT_START",
                DEFAULT_LOGIN_WEBSOCKIFY_PORT_START,
            ),
            novnc_root=os.getenv(
                "CAPTURE_LOGIN_NOVNC_ROOT",
                DEFAULT_LOGIN_NOVNC_DIRECTORY,
            ),
        )


def auth_profile_key() -> bytes:
    value = required(AUTH_PROFILE_KEY_ENVIRONMENT)

    try:
        key = base64.b64decode(value, validate=True)
    except binascii.Error as error:
        raise ValueError(f"{AUTH_PROFILE_KEY_ENVIRONMENT} must be base64") from error

    if len(key) != 32:
        raise ValueError(f"{AUTH_PROFILE_KEY_ENVIRONMENT} must decode to 32 bytes")

    return key
