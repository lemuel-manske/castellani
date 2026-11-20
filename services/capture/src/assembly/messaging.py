from adapters.messaging.rabbitmq.consumer import RabbitMQPageTaskConsumer
from application.worker import Worker


def new_rabbitmq_page_task_consumer(worker: Worker) -> RabbitMQPageTaskConsumer:
    return RabbitMQPageTaskConsumer(process_page=worker.execute)
