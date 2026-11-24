import os


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
