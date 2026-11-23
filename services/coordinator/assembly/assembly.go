// Package assembly connects Coordinator infrastructure to application use cases.
package assembly

import (
	"github.com/lemuel-manske/castellani/services/coordinator/application"
	"github.com/lemuel-manske/castellani/services/coordinator/messaging/dispatcher"
	"github.com/lemuel-manske/castellani/services/coordinator/messaging/rabbitmq"
	persistence "github.com/lemuel-manske/castellani/services/coordinator/persistence/dynamodb"
)

type Components struct {
	Application *application.Application
	Dispatcher  *dispatcher.Dispatcher
	Consumer    *rabbitmq.RabbitConsumer
}

func NewComponents(
	repository *persistence.DynamoRepository,
	rabbitURL string,
) Components {
	publisher := rabbitmq.NewRabbitPublisher(rabbitURL)

	return Components{
		Application: application.NewApplication(repository),
		Dispatcher:  dispatcher.NewDispatcher(repository, publisher),
		Consumer: rabbitmq.NewRabbitConsumer(
			rabbitURL,
			publisher,
		),
	}
}
