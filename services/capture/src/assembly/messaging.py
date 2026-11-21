from adapters.messaging.rabbitmq.consumer import RabbitMQPageTaskConsumer
from application.worker import ConcreteCaptureWorker


def new_rabbitmq_page_task_consumer(worker: ConcreteCaptureWorker) -> RabbitMQPageTaskConsumer:
    return RabbitMQPageTaskConsumer(page_capturer=worker.execute)
