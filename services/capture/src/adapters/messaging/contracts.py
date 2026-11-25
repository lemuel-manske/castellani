import json
import os
from functools import cache
from pathlib import Path
from typing import Any, cast

from jsonschema import FormatChecker
from jsonschema.validators import validator_for
from referencing import Registry, Resource

from .types import JSON

CONTRACT_DIR_ENV = "CAPTURE_CONTRACTS_DIR"

SCHEMA_DIRS = ("documents", "messages", "types")

SCHEMA_GLOB = "*.v1.schema.json"


def validate_message(body: bytes, message_type: str) -> JSON | None:
    contract_validators = validators()

    try:
        decoded: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(decoded, dict):
        return None

    validator = contract_validators.get(message_type)

    if validator is None or not validator.is_valid(decoded):
        return None

    return cast(JSON, decoded)


@cache
def validators() -> dict[str, Any]:
    contract_schemas = schemas()

    registry: Registry[Any] = Registry[Any]().with_resources(
        (identifier, Resource[Any].from_contents(schema))
        for identifier, schema in contract_schemas.items()
    )

    result: dict[str, Any] = {}

    format_checker = FormatChecker()

    for schema in contract_schemas.values():
        message_type = schema_message_type(schema)

        if message_type is None:
            continue

        validator_type = validator_for(schema)

        validator_type.check_schema(schema)

        result[message_type] = validator_type(
            schema,
            registry=registry,
            format_checker=format_checker,
        )

    return result


def schemas() -> dict[str, JSON]:
    root = Path(os.environ[CONTRACT_DIR_ENV])

    paths: list[Path] = []

    for directory in SCHEMA_DIRS:
        paths.extend(sorted((root / directory).glob(SCHEMA_GLOB)))

    loaded: dict[str, JSON] = {}

    for path in paths:
        schema = cast(JSON, json.loads(path.read_text()))

        loaded[schema["$id"]] = schema

    return loaded


def schema_message_type(schema: JSON) -> str | None:
    properties = cast(JSON, schema.get("properties", {}))
    type_schema = cast(JSON, properties.get("type", {}))
    message_type = type_schema.get("const")

    return message_type if isinstance(message_type, str) else None


__all__ = ["validate_message"]
