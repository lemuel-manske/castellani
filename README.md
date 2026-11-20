# Castellani

A self-hosted distributed system for crawling, preserving, and searching historical web content, including dynamic and authenticated pages.

Architecture and decisions: **[ADRs](docs/adr/README.md)**.

## Local backend stack

Requires Docker Compose. Terraform 1.16.5 and AWS provider 6.73.0 are pinned in `infra/terraform`; the Compose provisioner uses the pinned Terraform image.

```sh
docker compose up --build
```

The default local stack starts MiniStack, RabbitMQ, Terraform-provisioned DynamoDB/S3/OpenSearch resources, the Archive Coordinator, and the API Gateway. Capture and Search are separate service deployments and can be connected by setting `CAPTURE_URL` and `SEARCH_URL`.

The Gateway is exposed at `http://localhost:8080`; Coordinator is internal to the Compose network. MiniStack and RabbitMQ management interfaces are bound to loopback. MiniStack uses the Docker socket to start its real OpenSearch data plane; this is strictly for local development.
