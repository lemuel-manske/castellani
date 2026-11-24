# Castellani

A self-hosted distributed system for crawling, preserving, and searching historical web content, including dynamic and authenticated pages.

Architecture and decisions: **[ADRs](docs/adr/README.md)**.

## Running it

Requires Docker Compose.

```sh
docker compose up --build
```

The Gateway is exposed at `http://localhost:8080`.
