.PHONY: install run fmt check

install:
	go mod download


fmt:
	$(MAKE) -C ../codemods/go apply TARGET=../../tests


check:
	go vet ./...
	go build ./...


test:
	go test -v -timeout 30m ./...
