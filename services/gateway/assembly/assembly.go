// Package assembly connects concrete service clients to application-owned ports.
package assembly

import (
	"fmt"

	"github.com/lemuel-manske/unnamed/services/gateway/application"
	"github.com/lemuel-manske/unnamed/services/gateway/clients/capture"
	"github.com/lemuel-manske/unnamed/services/gateway/clients/coordinator"
	"github.com/lemuel-manske/unnamed/services/gateway/clients/search"
)

func NewApplication(
	coordinatorClient *coordinator.Client,
	captureClient *capture.Client,
	searchClient *search.Client,
) application.Application {
	var coordinatorPort application.CoordinatorService
	var capturePort application.CaptureService
	var searchPort application.SearchService

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

	if searchClient != nil {
		searchPort = searchAdapter{
			client: searchClient,
		}
	}

	return application.NewApplication(
		coordinatorPort,
		capturePort,
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
