.PHONY: install fmt test check

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
