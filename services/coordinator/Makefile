.PHONY: install run fmt check

install:
	go mod download


run:
	go run .


check:
	go vet ./...
	go build ./...

fmt:
	$(MAKE) -C ../../codemods/go apply TARGET=../../services/coordinator


test:
	go test -v ./...
