import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient

from adapters.persistence.dynamodb.alloc import DynamoDBCaptureAllocator
from ports.capture import CaptureAllocator
from ports.clock import Clock

LEASE_DURATION = 60.0
SLOT_COUNT = 2


@pytest.fixture
def capture_allocator(dynamodb: DynamoDBClient, clock: Clock) -> CaptureAllocator:
    return DynamoDBCaptureAllocator(
        dynamodb,
        slot_count=SLOT_COUNT,
        lease_duration=LEASE_DURATION,
        clock=clock,
    )
