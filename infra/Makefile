.PHONY: fmt validate plan apply destroy

# Every target runs the pinned Terraform image through the Compose `provision`
# service, so it shares the state volume and MiniStack network used by
# `docker compose up`. No local Terraform install is needed.
COMPOSE ?= docker compose -f ../docker-compose.yaml
TERRAFORM_IMAGE ?= hashicorp/terraform:1.16.5

fmt:
	docker run --rm -v "$(CURDIR)/terraform:/workspace" -w /workspace $(TERRAFORM_IMAGE) fmt -recursive

validate:
	$(COMPOSE) run --rm --no-deps provision "terraform init && terraform validate"

plan:
	$(COMPOSE) run --rm provision "terraform init && terraform plan"

apply:
	$(COMPOSE) run --rm provision "terraform init && terraform apply"

destroy:
	$(COMPOSE) run --rm provision "terraform init && terraform destroy"
