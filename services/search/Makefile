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

# Requires the Compose stack; run from a container on its network, e.g.
# docker run --rm --network castellani_default -v "$(CURDIR)/../..:/srv" \
#   -w /srv/services/search node:24.16.0-alpine3.22 sh -c "npm ci && npm run test:integration"
test-integration:
	npm run test:integration
