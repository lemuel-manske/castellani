# Castellani

A self-hosted distributed system for crawling, preserving, and searching historical web content, including dynamic and authenticated pages.

Architecture and decisions: **[ADRs](docs/adr/README.md)**.

## Running it

Requires Docker Compose. Terraform 1.16.5 and AWS provider 6.73.0 are pinned in `infra/terraform`; the Compose provisioner uses the pinned Terraform image.

```sh
docker compose up --build
```

The Gateway is exposed at `http://localhost:8080`.
