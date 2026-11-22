import os
from dataclasses import dataclass

DEFAULT_AWS_REGION = "us-east-1"

DEFAULT_BROWSER_SLOT_COUNT = 10

DEFAULT_LEASE_DURATION = 60.0

DEFAULT_OUTBOX_LEASE_DURATION = 30.0
DEFAULT_OUTBOX_POLL_INTERVAL = 0.5
DEFAULT_OUTBOX_RETRY_DELAY = 5.0

DEFAULT_ARTIFACT_DIRECTORY = "/tmp/castellani/capture"


@dataclass(frozen=True)
class CaptureSettings:
    """Runtime configuration for one Capture service process."""

    aws_region: str = DEFAULT_AWS_REGION

    dynamodb_endpoint_url: str | None = None
    rabbitmq_url: str | None = None
    s3_endpoint_url: str | None = None

    browser_slot_count: int = DEFAULT_BROWSER_SLOT_COUNT

    lease_duration: float = DEFAULT_LEASE_DURATION

    outbox_lease_duration: float = DEFAULT_OUTBOX_LEASE_DURATION
    outbox_poll_interval: float = DEFAULT_OUTBOX_POLL_INTERVAL
    outbox_retry_delay: float = DEFAULT_OUTBOX_RETRY_DELAY

    artifact_directory: str = DEFAULT_ARTIFACT_DIRECTORY

    @classmethod
    def from_environment(cls) -> "CaptureSettings":
        return cls(
            aws_region=os.getenv("AWS_REGION", DEFAULT_AWS_REGION),
            dynamodb_endpoint_url=os.getenv("DYNAMODB_ENDPOINT_URL"),
            rabbitmq_url=os.getenv("RABBITMQ_URL"),
            s3_endpoint_url=os.getenv("S3_ENDPOINT_URL"),
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
