# Archive Coordinator

The Archive Coordinator durably admits archive runs and owns workflow coordination across Capture and Search. The API Gateway forwards archive submissions and status requests to it.

## Development

Requires Go 1.25.4. From `services/coordinator`:

- `make install`: download dependencies.
- `make run`: start the Coordinator.
- `make fmt`: apply repository Go formatting conventions.
- `make check`: run static analysis and compile all packages without executing tests.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `COORDINATOR_ADDR` | `:8081` | HTTP listen address |
| `COORDINATOR_SHUTDOWN_TIMEOUT` | `10s` | Graceful shutdown deadline |
| `COORDINATOR_AWS_REGION` | `us-east-1` | AWS SDK region |
| `COORDINATOR_DYNAMODB_ENDPOINT` | unset | Optional DynamoDB-compatible endpoint |
| `COORDINATOR_ARCHIVES_TABLE` | `coordinator_archive_runs` | Archive table, partition key `archiveId`; recovery GSI `recoveryKey-updatedAt-index` |
| `COORDINATOR_SUBMISSIONS_TABLE` | `coordinator_submission_keys` | Idempotency table, partition key `idempotencyKey` |
| `COORDINATOR_OUTBOX_TABLE` | `coordinator_outbox` | Outbox table, partition key `messageId` |
| `COORDINATOR_INBOX_TABLE` | `coordinator_inbox` | Inbox table, partition key `messageId` |
| `COORDINATOR_RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | Message broker connection |
| `COORDINATOR_RABBITMQ_EXCHANGE` | `castellani.events` | Durable topic exchange |
| `COORDINATOR_RECONCILIATION_INTERVAL` | `30s` | Delay between stalled-workflow reconciliation passes |
| `COORDINATOR_STALLED_WORKFLOW_AGE` | `2m` | Minimum time without a state update before a SAGA decision is reissued |

## Recovery

The outbox dispatcher reclaims expired leases and republishes messages that were not confirmed by RabbitMQ. The consumer reconnects after failures and uses bounded delayed retries and dead-letter routing.

The reconciliation worker queries only recoverable archive decisions through the `recoveryKey-updatedAt-index`. It reissues `ArchivePublicationDecided` for stalled `PUBLISH` runs and `ArchiveCompensationDecided` for stalled `COMPENSATE` runs. The outbox insert and archive revision/cooldown update are one DynamoDB transaction, preventing multiple Coordinator replicas from continually scheduling the same recovery command.

Recovery is intentionally limited to decisions already committed by the Coordinator. It does not infer crawl completion, recreate a missing crawl frontier, or repair Search's index. Capture and Search must reconcile their own durable side effects, and their command handlers must be idempotent by archive ID and decision version.
