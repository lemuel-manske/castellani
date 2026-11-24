#!/usr/bin/env python3
"""Apply the centralized RabbitMQ topology through the Management API."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ALLOWED_EXCHANGE_TYPES = {"direct", "fanout", "headers", "topic"}


class ProvisionError(Exception):
    """Raised when the topology or the broker state cannot be applied."""


def management_request(
    method: str,
    url: str,
    path: str,
    authorization: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode()

    request = urllib.request.Request(
        url + path,
        data=data,
        method=method,
        headers={
            "Authorization": authorization,
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read()

            return json.loads(body) if body else None
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None

        detail = error.read().decode(errors="replace")

        raise ProvisionError(
            f"{method} {path} failed: HTTP {error.code}: {detail}"
        ) from error
    except urllib.error.URLError as error:
        raise ProvisionError(f"{method} {path} failed: {error.reason}") from error


def load_topology(path: Path) -> dict[str, Any]:
    try:
        topology = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ProvisionError(f"cannot read topology {path}: {error}") from error

    if not isinstance(topology, dict):
        raise ProvisionError("topology must be a JSON object")

    for key in ("vhost", "exchanges", "queues", "bindings"):
        if key not in topology:
            raise ProvisionError(f"topology is missing {key!r}")

    exchanges = topology["exchanges"]
    queues = topology["queues"]
    bindings = topology["bindings"]

    if not all(isinstance(group, list) for group in (exchanges, queues, bindings)):
        raise ProvisionError("exchanges, queues, and bindings must be arrays")

    exchange_names: set[str] = set()
    queue_names: set[str] = set()

    for exchange in exchanges:
        name = exchange.get("name")
        kind = exchange.get("type")

        if not isinstance(name, str) or not name:
            raise ProvisionError("every exchange needs a non-empty name")

        if kind not in ALLOWED_EXCHANGE_TYPES:
            raise ProvisionError(f"exchange {name} has unsupported type {kind!r}")

        if name in exchange_names:
            raise ProvisionError(f"duplicate exchange {name}")

        exchange_names.add(name)

    for queue in queues:
        name = queue.get("name")

        if not isinstance(name, str) or not name:
            raise ProvisionError("every queue needs a non-empty name")

        if name in queue_names:
            raise ProvisionError(f"duplicate queue {name}")

        queue_names.add(name)

    for binding in bindings:
        if binding.get("exchange") not in exchange_names:
            raise ProvisionError(
                f"binding references unknown exchange {binding.get('exchange')!r}"
            )

        if binding.get("queue") not in queue_names:
            raise ProvisionError(
                f"binding references unknown queue {binding.get('queue')!r}"
            )

        keys = binding.get("routingKeys")

        if not isinstance(keys, list) or not all(isinstance(key, str) for key in keys):
            raise ProvisionError("every binding needs a routingKeys array of strings")

    return topology


def encoded(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def assert_compatible(
    kind: str,
    name: str,
    current: dict[str, Any] | None,
    expected: dict[str, Any],
) -> bool:
    if current is None:
        return False

    conflicts = {
        key: {"expected": value, "actual": current.get(key)}
        for key, value in expected.items()
        if current.get(key) != value
    }

    if conflicts:
        raise ProvisionError(
            f"existing {kind} {name} is incompatible: "
            f"{json.dumps(conflicts, sort_keys=True)}"
        )

    return True


def provision_exchange(
    topology: dict[str, Any],
    vhost: str,
    url: str,
    authorization: str,
    exchange: dict[str, Any],
) -> None:
    name = exchange["name"]
    path = f"/api/exchanges/{encoded(vhost)}/{encoded(name)}"
    expected = {
        "type": exchange["type"],
        "durable": exchange.get("durable", True),
        "auto_delete": False,
        "internal": False,
        "arguments": exchange.get("arguments", {}),
    }

    current = management_request("GET", url, path, authorization)

    if assert_compatible("exchange", name, current, expected):
        print(f"exchange {name}: unchanged")
        return

    management_request("PUT", url, path, authorization, expected)
    print(f"exchange {name}: created")


def provision_queue(
    topology: dict[str, Any],
    vhost: str,
    url: str,
    authorization: str,
    queue: dict[str, Any],
) -> None:
    name = queue["name"]
    path = f"/api/queues/{encoded(vhost)}/{encoded(name)}"
    expected = {
        "durable": queue.get("durable", True),
        "auto_delete": False,
        "arguments": queue.get("arguments", {}),
    }

    current = management_request("GET", url, path, authorization)

    if assert_compatible("queue", name, current, expected):
        print(f"queue {name}: unchanged")
        return

    management_request("PUT", url, path, authorization, expected)
    print(f"queue {name}: created")


def provision_binding(
    vhost: str,
    url: str,
    authorization: str,
    binding: dict[str, Any],
    routing_key: str,
) -> None:
    exchange = binding["exchange"]
    queue = binding["queue"]

    path = (
        f"/api/bindings/{encoded(vhost)}/e/{encoded(exchange)}"
        f"/q/{encoded(queue)}"
    )

    current = management_request("GET", url, path, authorization) or []

    if any(
        item.get("routing_key") == routing_key and item.get("arguments") in ({}, None)
        for item in current
    ):
        print(f"binding {exchange} -> {queue} [{routing_key}]: unchanged")
        return

    management_request(
        "POST",
        url,
        path,
        authorization,
        {"routing_key": routing_key, "arguments": {}},
    )
    print(f"binding {exchange} -> {queue} [{routing_key}]: created")


def provision(topology: dict[str, Any], url: str, authorization: str) -> None:
    vhost = topology["vhost"]

    for exchange in topology["exchanges"]:
        provision_exchange(topology, vhost, url, authorization, exchange)

    for queue in topology["queues"]:
        provision_queue(topology, vhost, url, authorization, queue)

    for binding in topology["bindings"]:
        for routing_key in binding["routingKeys"]:
            provision_binding(vhost, url, authorization, binding, routing_key)


def authorization_header(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)

    username = os.getenv("RABBITMQ_USERNAME", parsed.username or "guest")
    password = os.getenv("RABBITMQ_PASSWORD", parsed.password or "guest")

    credentials = f"{urllib.parse.unquote(username)}:{urllib.parse.unquote(password)}"

    return "Basic " + base64.b64encode(credentials.encode()).decode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "topology",
        nargs="?",
        type=Path,
        default=Path(__file__).with_name("topology.json"),
    )
    args = parser.parse_args()

    url = os.getenv(
        "RABBITMQ_MANAGEMENT_URL",
        "http://localhost:15672",
    ).rstrip("/")

    try:
        topology = load_topology(args.topology)
        provision(topology, url, authorization_header(url))
    except ProvisionError as error:
        print(f"rabbitmq provisioning failed: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
