.PHONY: init fmt validate plan apply destroy

TERRAFORM ?= terraform

init:
	$(TERRAFORM) -chdir=terraform init -lockfile=readonly

fmt:
	$(TERRAFORM) -chdir=terraform fmt -recursive

validate: init
	$(TERRAFORM) -chdir=terraform validate

plan: init
	$(TERRAFORM) -chdir=terraform plan

apply: init
	$(TERRAFORM) -chdir=terraform apply

destroy: init
	$(TERRAFORM) -chdir=terraform destroy
