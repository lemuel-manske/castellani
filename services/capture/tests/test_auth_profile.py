import pytest
from cryptography.exceptions import InvalidTag
from mypy_boto3_dynamodb.client import DynamoDBClient
from support.s3 import FakeS3

from adapters.artifacts.auth import AuthProfileCipher, EncryptedAuthProfileStore
from domain import AuthProfileStore

STATE = {"cookies": [{"name": "session", "value": "opaque"}], "origins": []}


def test_profile_cipher_round_trips_a_storage_state() -> None:
    cipher = new_cipher()

    assert cipher.decrypt(cipher.encrypt(STATE)) == STATE


def test_profile_cipher_rejects_a_tampered_ciphertext() -> None:
    cipher = new_cipher()
    ciphertext = bytearray(cipher.encrypt(STATE))
    ciphertext[-1] ^= 1

    with pytest.raises(InvalidTag):
        cipher.decrypt(bytes(ciphertext))


async def test_profile_store_encrypts_state_under_a_generation_key(s3: FakeS3) -> None:
    store = new_store(s3, None)

    key = await store.save("archive-1", 2, STATE)
    loaded = await store.load(key)
    raw = s3.objects[("castellani-auth-profiles", key)][0]

    assert (key, loaded, b"opaque" in raw) == (
        "auth-profiles/archive-1/generation-2.json.enc",
        STATE,
        False,
    )


@pytest.mark.integration
async def test_profile_store_loads_the_latest_generation(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
) -> None:
    store = new_store(s3, dynamodb)
    key = await store.save("archive-1", 1, STATE)
    dynamodb.update_item(
        TableName="capture_runs",
        Key={"archiveId": {"S": "archive-1"}},
        UpdateExpression="SET authGeneration = :generation, authProfileKey = :key",
        ExpressionAttributeValues={
            ":generation": {"N": "1"},
            ":key": {"S": key},
        },
    )

    assert await store.load_latest("archive-1") == STATE


def new_cipher() -> AuthProfileCipher:
    return AuthProfileCipher(b"0" * 32)


def new_store(s3: FakeS3, dynamodb: DynamoDBClient | None) -> AuthProfileStore:
    return EncryptedAuthProfileStore(
        s3_client=s3,
        dynamodb_client=dynamodb,
        bucket="castellani-auth-profiles",
        cipher=new_cipher(),
    )
