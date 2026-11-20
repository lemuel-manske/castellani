from application.worker import Worker
from adapters.messaging.rabbitmq.consumer import RabbitMQPageTaskConsumer


def new_rabbitmq_page_task_consumer(worker: Worker) -> RabbitMQPageTaskConsumer:
    return RabbitMQPageTaskConsumer(process_page=worker.execute)
