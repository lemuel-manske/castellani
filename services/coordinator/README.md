# Archive Coordinator

The Coordinator owns durable archive admission, public operation status, and the cross-service archive SAGA. It uses its own DynamoDB tables and communicates downstream through versioned messages; the Gateway forwards admission and status HTTP requests.

The initial implementation provides transactional submission registration, idempotency-key replay, and durable StartCrawl outbox insertion. **The outbox dispatcher and incoming SAGA event processing are not yet implemented**, so registering an archive does not yet initiate crawling.

Configuration: `COORDINATOR_ADDR` (default `:8081`), `COORDINATOR_TABLE_PREFIX`, and AWS SDK environment/profile configuration. Create the three Coordinator-owned DynamoDB tables before starting: `coordinator_archive_runs` (string `archiveId`), `coordinator_submission_keys` (string `idempotencyKey`), and `coordinator_outbox` (string `messageId`). Prefix names with `COORDINATOR_TABLE_PREFIX` where configured.

Run `make install`, `make run`, `make test`, or `make check`. Architecture and correctness constraints are documented in `docs/adr/`, `docs/backend/`, and `contracts/`.
