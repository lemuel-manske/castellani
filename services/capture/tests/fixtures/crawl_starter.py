import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient

from adapters.persistence.dynamodb.run import DynamoDBRunStarter
from ports.capture import CrawlStarter
from ports.clock import Clock


@pytest.fixture
def crawl_starter(dynamodb: DynamoDBClient, clock: Clock) -> CrawlStarter:
    return DynamoDBRunStarter(dynamodb, clock=clock)
