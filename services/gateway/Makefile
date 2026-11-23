.PHONY: install run fmt check

install:
	go mod download


run:
	go run .


fmt:
	$(MAKE) -C ../../codemods/go apply TARGET=../../services/gateway

check:
	go vet ./...
	go test -race ./...
