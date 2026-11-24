
resource "aws_dynamodb_table" "coordinator_archives" {
  name         = "coordinator_archives"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "archiveId"

  attribute {
    name = "archiveId"
    type = "S"
  }

  attribute {
    name = "recoveryKey"
    type = "S"
  }

  attribute {
    name = "updatedAt"
    type = "S"
  }

  global_secondary_index {
    name            = "recoveryKey-updatedAt-index"
    projection_type = "ALL"

    key_schema {
      attribute_name = "recoveryKey"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "updatedAt"
      key_type       = "RANGE"
    }
  }
}

resource "aws_dynamodb_table" "coordinator_submissions" {
  name         = "coordinator_submissions"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "idempotencyKey"

  attribute {
    name = "idempotencyKey"
    type = "S"
  }

  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }
}

resource "aws_dynamodb_table" "coordinator_outbox" {
  name         = "coordinator_outbox"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "messageId"

  attribute {
    name = "messageId"
    type = "S"
  }
}

resource "aws_dynamodb_table" "coordinator_inbox" {
  name         = "coordinator_inbox"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "messageId"

  attribute {
    name = "messageId"
    type = "S"
  }
}

resource "aws_dynamodb_table" "capture_runs" {
  name         = "capture_runs"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "archiveId"

  attribute {
    name = "archiveId"
    type = "S"
  }
}

resource "aws_dynamodb_table" "capture_frontier" {
  name         = "capture_frontier"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "archiveId"
  range_key = "urlKey"

  attribute {
    name = "archiveId"
    type = "S"
  }

  attribute {
    name = "urlKey"
    type = "S"
  }
}

resource "aws_dynamodb_table" "capture_outbox" {
  name         = "capture_outbox"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "messageId"

  attribute {
    name = "messageId"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "nextAttemptAt"
    type = "N"
  }

  global_secondary_index {
    name            = "status-nextAttemptAt-index"
    projection_type = "ALL"

    key_schema {
      attribute_name = "status"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "nextAttemptAt"
      key_type       = "RANGE"
    }
  }
}

resource "aws_dynamodb_table" "capture_browser_slots" {
  name         = "capture_browser_slots"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "slotId"

  attribute {
    name = "slotId"
    type = "S"
  }
}

resource "aws_dynamodb_table" "capture_snapshots" {
  name         = "capture_snapshots"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "snapshotId"

  attribute {
    name = "snapshotId"
    type = "S"
  }

  attribute {
    name = "archiveId"
    type = "S"
  }

  attribute {
    name = "capturedAt"
    type = "S"
  }

  global_secondary_index {
    name            = "archiveId-capturedAt-index"
    projection_type = "ALL"

    key_schema {
      attribute_name = "archiveId"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "capturedAt"
      key_type       = "RANGE"
    }
  }
}

resource "aws_dynamodb_table" "capture_sessions" {
  name         = "capture_sessions"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "sessionId"

  attribute {
    name = "sessionId"
    type = "S"
  }

  ttl {
    attribute_name = "expiresAtEpoch"
    enabled        = true
  }
}

resource "aws_dynamodb_table" "capture_session_requests" {
  name         = "capture_session_requests"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "idempotencyKey"

  attribute {
    name = "idempotencyKey"
    type = "S"
  }

  ttl {
    attribute_name = "expiresAtEpoch"
    enabled        = true
  }
}

resource "aws_dynamodb_table" "search_indexing_ledger" {
  name         = "search_indexing_ledger"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "snapshotId"

  attribute {
    name = "snapshotId"
    type = "S"
  }

  attribute {
    name = "archiveId"
    type = "S"
  }

  global_secondary_index {
    name            = "archiveId-snapshotId-index"
    projection_type = "ALL"

    key_schema {
      attribute_name = "archiveId"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "snapshotId"
      key_type       = "RANGE"
    }
  }
}

resource "aws_dynamodb_table" "search_publication_ledger" {
  name         = "search_publication_ledger"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "archiveId"

  attribute {
    name = "archiveId"
    type = "S"
  }
}

resource "aws_dynamodb_table" "search_manifest_ledger" {
  name         = "search_manifest_ledger"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "archiveId"
  range_key = "snapshotId"

  attribute {
    name = "archiveId"
    type = "S"
  }

  attribute {
    name = "snapshotId"
    type = "S"
  }
}

resource "aws_s3_bucket" "archive_artifacts" {
  bucket        = "castellani-archive-artifacts"
  force_destroy = true
}

resource "aws_s3_bucket" "archive_manifests" {
  bucket        = "castellani-archive-manifests"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "archive_artifacts" {
  bucket = aws_s3_bucket.archive_artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_versioning" "archive_manifests" {
  bucket = aws_s3_bucket.archive_manifests.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "archive_artifacts" {
  bucket = aws_s3_bucket.archive_artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "archive_manifests" {
  bucket = aws_s3_bucket.archive_manifests.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "auth_profiles" {
  bucket        = "castellani-auth-profiles"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "auth_profiles" {
  bucket = aws_s3_bucket.auth_profiles.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "auth_profiles" {
  bucket = aws_s3_bucket.auth_profiles.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "auth_profiles" {
  bucket = aws_s3_bucket.auth_profiles.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
