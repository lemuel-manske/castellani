// Package assembly connects concrete service clients to application-owned ports.
package assembly

import (
	"fmt"

	"github.com/lemuel-manske/castellani/services/gateway/application"
	"github.com/lemuel-manske/castellani/services/gateway/clients/capture"
	"github.com/lemuel-manske/castellani/services/gateway/clients/coordinator"
	"github.com/lemuel-manske/castellani/services/gateway/clients/login"
	"github.com/lemuel-manske/castellani/services/gateway/clients/search"
)

func NewApplication(
	coordinatorClient *coordinator.Client,
	captureClient *capture.Client,
	loginClient *login.Client,
	searchClient *search.Client,
) application.Application {
	var coordinatorPort application.Coordinator
	var capturePort application.Capture
	var loginPort application.Login
	var searchPort application.Search

	if coordinatorClient != nil {
		coordinatorPort = coordinatorAdapter{
			client: coordinatorClient,
		}
	}

	if captureClient != nil {
		capturePort = captureAdapter{
			client: captureClient,
		}
	}

	if loginClient != nil {
		loginPort = loginAdapter{
			client: loginClient,
		}
	}

	if searchClient != nil {
		searchPort = searchAdapter{
			client: searchClient,
		}
	}

	return application.NewApplication(
		coordinatorPort,
		capturePort,
		loginPort,
		searchPort,
	)
}

func errUnavailable(err error) error {
	return fmt.Errorf(
		"%w: %v",
		application.ErrDependencyUnavailable,
		err,
	)
}
