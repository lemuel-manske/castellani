.PHONY: fmt test build run

install:
	$(MAKE) -C libs/httpx install
	$(MAKE) -C services/gateway install

fmt:
	$(MAKE) -C libs/httpx fmt
	$(MAKE) -C services/gateway fmt

test:
	$(MAKE) -C libs/httpx test
	$(MAKE) -C services/gateway test

check:
	$(MAKE) -C libs/httpx check
	$(MAKE) -C services/gateway check
