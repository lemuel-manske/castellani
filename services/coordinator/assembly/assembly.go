// Package assembly connects Coordinator infrastructure to application use cases.
package assembly

import (
	"github.com/lemuel-manske/unnamed/services/coordinator/application"
	"github.com/lemuel-manske/unnamed/services/coordinator/messaging/rabbitmq"
	persistence "github.com/lemuel-manske/unnamed/services/coordinator/persistence/dynamodb"
)

type Components struct {
	Application *application.Application
	Dispatcher  *application.Dispatcher
	Consumer    *rabbitmq.RabbitConsumer
}

func NewComponents(
	repository *persistence.DynamoArchiveRepository,
	rabbitURL string,
	rabbitExchange string,
) Components {
	publisher := rabbitmq.NewRabbitPublisher(rabbitURL, rabbitExchange)

	return Components{
		Application: application.NewApplication(repository, repository),
		Dispatcher:  application.NewDispatcher(repository, publisher),
		Consumer:    rabbitmq.NewRabbitConsumer(rabbitURL, rabbitExchange, publisher),
	}
}
