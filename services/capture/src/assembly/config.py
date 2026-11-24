import base64
import binascii
import os
import uuid
from dataclasses import dataclass, field

from domain import AUTH_PROFILE_BUCKET

DEFAULT_BROWSER_SLOT_COUNT = 10

AUTH_PROFILE_KEY_ENVIRONMENT = "CAPTURE_AUTH_PROFILE_KEY"

DEFAULT_LOGIN_PORT = 8010
DEFAULT_SESSION_TTL_SECONDS = 1800
DEFAULT_LOGIN_MAX_SESSIONS = 4
DEFAULT_LOGIN_DISPLAY_START = 100
DEFAULT_LOGIN_VNC_PORT_START = 5900
DEFAULT_LOGIN_WEBSOCKIFY_PORT_START = 6080
DEFAULT_LOGIN_NOVNC_ROOT = "/usr/share/novnc"

DEFAULT_LEASE_DURATION = 60.0

DEFAULT_OUTBOX_LEASE_DURATION = 30.0
DEFAULT_OUTBOX_POLL_INTERVAL = 0.5
DEFAULT_OUTBOX_RETRY_DELAY = 5.0

DEFAULT_ARTIFACT_DIRECTORY = "/tmp/castellani/capture"


@dataclass(frozen=True)
class CaptureSettings:
    """Runtime configuration for one Capture service process."""

    aws_region: str
    aws_access_key_id: str
    aws_secret_access_key: str

    dynamodb_endpoint_url: str
    rabbitmq_url: str
    s3_endpoint_url: str

    browser_slot_count: int = DEFAULT_BROWSER_SLOT_COUNT

    lease_duration: float = DEFAULT_LEASE_DURATION

    outbox_lease_duration: float = DEFAULT_OUTBOX_LEASE_DURATION
    outbox_poll_interval: float = DEFAULT_OUTBOX_POLL_INTERVAL
    outbox_retry_delay: float = DEFAULT_OUTBOX_RETRY_DELAY

    artifact_directory: str = DEFAULT_ARTIFACT_DIRECTORY

    @classmethod
    def from_environment(cls) -> "CaptureSettings":
        return cls(
            aws_region=required("CAPTURE_AWS_REGION"),
            aws_access_key_id=required("CAPTURE_AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=required("CAPTURE_AWS_SECRET_ACCESS_KEY"),
            dynamodb_endpoint_url=required("CAPTURE_DYNAMODB_ENDPOINT_URL"),
            rabbitmq_url=required("CAPTURE_RABBITMQ_URL"),
            s3_endpoint_url=required("CAPTURE_S3_ENDPOINT_URL"),
            browser_slot_count=positive_int(
                "CAPTURE_BROWSER_SLOT_COUNT",
                DEFAULT_BROWSER_SLOT_COUNT,
            ),
            lease_duration=positive_float(
                "CAPTURE_LEASE_DURATION_SECONDS",
                DEFAULT_LEASE_DURATION,
            ),
            outbox_lease_duration=positive_float(
                "CAPTURE_OUTBOX_LEASE_SECONDS",
                DEFAULT_OUTBOX_LEASE_DURATION,
            ),
            outbox_poll_interval=positive_float(
                "CAPTURE_OUTBOX_POLL_SECONDS",
                DEFAULT_OUTBOX_POLL_INTERVAL,
            ),
            outbox_retry_delay=positive_float(
                "CAPTURE_OUTBOX_RETRY_SECONDS",
                DEFAULT_OUTBOX_RETRY_DELAY,
            ),
            artifact_directory=os.getenv(
                "CAPTURE_ARTIFACT_DIRECTORY",
                DEFAULT_ARTIFACT_DIRECTORY,
            ),
        )


@dataclass(frozen=True)
class LoginSettings:
    """Runtime configuration for the dedicated interactive-login manager."""

    aws_region: str
    aws_access_key_id: str
    aws_secret_access_key: str
    dynamodb_endpoint_url: str
    s3_endpoint_url: str
    auth_profile_key: bytes
    auth_profile_bucket: str
    port: int
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
            aws_region=required("CAPTURE_AWS_REGION"),
            aws_access_key_id=required("CAPTURE_AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=required("CAPTURE_AWS_SECRET_ACCESS_KEY"),
            dynamodb_endpoint_url=required("CAPTURE_DYNAMODB_ENDPOINT_URL"),
            s3_endpoint_url=required("CAPTURE_S3_ENDPOINT_URL"),
            auth_profile_key=auth_profile_key(),
            auth_profile_bucket=os.getenv(
                "CAPTURE_AUTH_PROFILE_BUCKET",
                AUTH_PROFILE_BUCKET,
            ),
            port=positive_int("CAPTURE_LOGIN_PORT", DEFAULT_LOGIN_PORT),
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
                DEFAULT_LOGIN_NOVNC_ROOT,
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


def required(name: str) -> str:
    value = os.getenv(name)

    if value is None or not value.strip():
        raise ValueError(f"{name} is required")

    return value


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
