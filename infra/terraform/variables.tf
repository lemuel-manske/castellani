variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "ministack_endpoint" {
  type    = string
  default = "http://localhost:4566"

  validation {
    condition     = can(regex("^http://(localhost|127\\.0\\.0\\.1|ministack)(:[0-9]+)?/?$", var.ministack_endpoint))
    error_message = "This configuration is local-only: ministack_endpoint must point at the MiniStack emulator (localhost, 127.0.0.1 or the `ministack` Compose service)."
  }
}
