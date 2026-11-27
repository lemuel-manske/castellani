from collections.abc import Mapping
from typing import Any, cast


def string_from_item(item: dict[str, Any], key: str, resource: str) -> str:
    value = item.get(key, {}).get("S")

    if not isinstance(value, str):
        raise RuntimeError(f"DynamoDB {resource} has an invalid {key}")

    return value


def number_from_item(
    item: dict[str, Any],
    key: str,
    resource: str,
    default: int | float | None = None,
) -> int | float:
    try:
        number = float(item[key]["N"])
    except KeyError as error:
        if default is not None:
            return default

        raise RuntimeError(f"DynamoDB {resource} has an invalid {key}") from error
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"DynamoDB {resource} has an invalid {key}") from error

    return int(number) if number.is_integer() else number


def optional_number(item: dict[str, Any], key: str) -> int | None:
    value = item.get(key)

    return int(value["N"]) if value else None


def optional_string(item: dict[str, Any], key: str) -> str | None:
    value = item.get(key)

    return value["S"] if value else None


def envelope_matches(
    item: dict[str, Any],
    message_type: str,
    archive_id: str,
    payload: Mapping[str, Any],
) -> bool:
    stored = item.get("payload", {}).get("M", {})

    return (
        item.get("type", {}).get("S") == message_type
        and item.get("correlationId", {}).get("S") == archive_id
        and all(stored.get(key) == value for key, value in payload.items())
    )


def serialize_map(value: Mapping[str, object]) -> dict[str, Any]:
    return {key: serialize_attribute(item) for key, item in value.items()}


def serialize_attribute(value: object) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"BOOL": value}

    if isinstance(value, str):
        return {"S": value}

    if isinstance(value, int):
        return {"N": str(value)}

    if isinstance(value, dict):
        return {"M": serialize_map(cast(dict[str, object], value))}

    if isinstance(value, list):
        return {"L": [serialize_attribute(item) for item in cast(list[object], value)]}

    raise TypeError(f"unsupported DynamoDB message value: {type(value).__name__}")


def deserialize_attribute(attribute: dict[str, Any]) -> Any:
    if "S" in attribute:
        return attribute["S"]

    if "N" in attribute:
        number = float(attribute["N"])
        return int(number) if number.is_integer() else number

    if "BOOL" in attribute:
        return attribute["BOOL"]

    if "NULL" in attribute:
        return None

    if "M" in attribute:
        return {key: deserialize_attribute(value) for key, value in attribute["M"].items()}

    if "L" in attribute:
        return [deserialize_attribute(value) for value in attribute["L"]]

    raise RuntimeError("DynamoDB record contains an unsupported attribute type")


def plain_attributes(item: dict[str, Any]) -> dict[str, Any]:
    return {key: deserialize_attribute(value) for key, value in item.items()}
