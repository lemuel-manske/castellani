.PHONY: install run fmt test check

ifneq (,$(wildcard .env))
  include .env
  export
endif

install:
	go mod download

run:
	go run .

fmt:
	$(MAKE) -C ../../codemods/go apply TARGET=../../services/gateway

test:
	go test ./...

check:
	go vet ./...
	go test -race ./...
