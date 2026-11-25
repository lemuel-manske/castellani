import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient
from mypy_boto3_s3.client import S3Client
from support.domain import seed_run, set_run_auth_profile

from adapters.artifacts.auth import AuthProfileCipher, EncryptedAuthProfileStore
from adapters.persistence.dynamodb.session import DynamoDBSessionStore
from application.capture import StoredAuthContexts
from domain.capture import DEFAULT_AUTH_GENERATION, AuthContext


@pytest.mark.integration
async def test_stored_auth_contexts_defaults_to_an_unauthenticated_context(
    dynamodb: DynamoDBClient,
    s3: S3Client,
) -> None:
    seed_run(dynamodb)

    contexts = StoredAuthContexts(
        sessions=DynamoDBSessionStore(client=dynamodb),
        profiles=EncryptedAuthProfileStore(s3, AuthProfileCipher(b"k" * 32)),
    )

    assert await contexts.load("archive-1") == AuthContext(generation=DEFAULT_AUTH_GENERATION)


@pytest.mark.integration
async def test_stored_auth_contexts_loads_a_versioned_protected_profile(
    dynamodb: DynamoDBClient,
    s3: S3Client,
) -> None:
    seed_run(dynamodb)

    profiles = EncryptedAuthProfileStore(s3, AuthProfileCipher(b"k" * 32))

    state: dict[str, list[str]] = {"cookies": [], "origins": []}

    key = await profiles.save("archive-1", 2, state)
    set_run_auth_profile(dynamodb, 2, key)

    contexts = StoredAuthContexts(
        sessions=DynamoDBSessionStore(client=dynamodb),
        profiles=profiles,
    )

    context = await contexts.load("archive-1")

    assert context == AuthContext(generation=2, storage_state=state)
