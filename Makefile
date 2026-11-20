.PHONY: install fmt test check infra-init infra-validate infra-apply infra-destroy

install:
	$(MAKE) -C libs/httpx install
	$(MAKE) -C services/gateway install
	$(MAKE) -C services/coordinator install

fmt:
	$(MAKE) -C codemods/go fmt
	$(MAKE) -C libs/httpx fmt
	$(MAKE) -C services/gateway fmt
	$(MAKE) -C services/coordinator fmt

test:
	$(MAKE) -C codemods/go test
	$(MAKE) -C libs/httpx test
	$(MAKE) -C services/gateway test

check:
	$(MAKE) -C codemods/go check
	$(MAKE) -C libs/httpx check
	$(MAKE) -C services/gateway check
	$(MAKE) -C services/coordinator check

infra-init:
	$(MAKE) -C infra init

infra-validate:
	$(MAKE) -C infra validate

infra-apply:
	$(MAKE) -C infra apply

infra-destroy:
	$(MAKE) -C infra destroy
