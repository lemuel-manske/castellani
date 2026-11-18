# Distributed Web Archive

A self-hosted distributed system for crawling, preserving, and searching historical web content, including dynamic and authenticated pages. Go coordinates asynchronous archive runs, Python Capture workers discover and record pages into WARC/WACZ, and a TypeScript service indexes searchable snapshots. RabbitMQ distributes work; DynamoDB, S3, and OpenSearch provide durable state, archival storage, and retrieval.

Architecture and decisions: **[ADRs](docs/adr/README.md)**. Implementation-facing specifications: [backend invariants and recovery](docs/backend/README.md), [HTTP API](contracts/openapi/api.yaml), and [message contracts](contracts/messages/README.md).
