# Local infrastructure

Terraform provisions the Coordinator-owned DynamoDB tables, private versioned S3 artifact and manifest buckets, and the OpenSearch domain used by Search.

The provider is pinned to AWS provider 6.73.0 and Terraform CLI 1.16.5. The provider lockfile is committed with checksums for supported platforms. Initialization uses `-lockfile=readonly`; update the provider version and lockfile together when upgrading.

For a local host shell:

```sh
terraform init
terraform apply
```

For Docker Compose, the provisioner uses `http://ministack:4566` as the AWS-compatible endpoint. The OpenSearch domain requires MiniStack's `OPENSEARCH_DATAPLANE=1` setting so the control-plane resource is backed by a real OpenSearch container.

The MiniStack container mounts the Docker socket to create that data-plane container. This is a local-development-only privilege and must not be carried into a production deployment.
