.PHONY: install fmt test check

install:
	go mod download

fmt:
	$(MAKE) -C ../../codemods/go apply TARGET=../../libs/httpx

test:
	go test ./...

check:
	go vet ./...
	go test -race ./...
