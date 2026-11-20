# Local Terraform (MiniStack only)

This configuration provisions the DynamoDB tables, S3 buckets and OpenSearch domain that the local stack needs, **inside the MiniStack emulator**. It is not a production deployment and must not be applied to a real AWS account.

It is local-only because:

- the provider uses dummy credentials (`test`/`test`) and endpoint overrides; `ministack_endpoint` is validated to accept only `localhost`, `127.0.0.1` or the `ministack` Compose service;
- the OpenSearch access policy allows any principal and HTTPS is not enforced;
- buckets use `force_destroy = true`;
- the account ID is MiniStack's fixed `000000000000`.

A real AWS environment needs its own configuration (remote state, real credentials, least-privilege policies, encryption, HTTPS-only endpoints) rather than an edited copy of this one.

## Usage

`docker compose up` applies it automatically through the `provision` service. For ad-hoc commands use `make -C infra plan|apply|destroy|validate|fmt`, which go through the same container and state volume. See [operations](../../docs/backend/operations.md#deployment-and-recovery-boundaries).
