# LOCAL-ONLY. This provider targets the MiniStack emulator with dummy
# credentials; `ministack_endpoint` is validated to reject anything else.
# Do not point it at real AWS: see README.md in this directory.
provider "aws" {
  region = var.aws_region

  access_key = "test"
  secret_key = "test"

  s3_use_path_style           = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    dynamodb   = var.ministack_endpoint
    s3         = var.ministack_endpoint
    opensearch = var.ministack_endpoint
  }
}
