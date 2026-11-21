from typing import Any


def string_from_item(item: dict[str, Any], key: str, resource: str) -> str:
    value = item.get(key, {}).get("S")

    if not isinstance(value, str):
        raise RuntimeError(f"DynamoDB {resource} has an invalid {key}")

    return value


def number_from_item(item: dict[str, Any], key: str, resource: str) -> int | float:
    try:
        number = float(item[key]["N"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f"DynamoDB {resource} has an invalid {key}") from error

    return int(number) if number.is_integer() else number


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
