.PHONY: install run fmt test test-integration check

install:
	npm ci


run:
	npm run build && npm start


fmt:
	npm run format

check:
	npm run format:check
	npm run typecheck
	npm run lint


test:
	npm test

test-integration:
	npm run test:integration
