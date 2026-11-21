terraform {
  required_version = "= 1.16.5"

  # The state path is supplied at init time (see TF_CLI_ARGS_init in
  # docker-compose.yaml) so it lives in the `terraform-state` volume.
  backend "local" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.73.0"
    }
  }
}
