module github.com/lemuel-manske/unnamed/services/gateway

go 1.25.0

toolchain go1.25.4

require (
	github.com/lemuel-manske/castellani/libs/httpx v0.0.0
	github.com/go-chi/chi/v5 v5.2.3
	github.com/stretchr/testify v1.10.0
)

require (
	github.com/davecgh/go-spew v1.1.1 // indirect
	github.com/pmezard/go-difflib v1.0.0 // indirect
	gopkg.in/yaml.v3 v3.0.1 // indirect
)

replace github.com/lemuel-manske/castellani/libs/httpx => ../../libs/httpx
