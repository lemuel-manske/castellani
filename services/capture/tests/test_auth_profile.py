import pytest
from cryptography.exceptions import InvalidTag
from support.s3 import FakeS3

from adapters.artifacts.auth import AuthProfileCipher, EncryptedAuthProfileStore
from buckets import AUTH_PROFILE_BUCKET
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
    store = new_store(s3)

    key = await store.save("archive-1", 2, STATE)
    loaded = await store.load(key)
    raw = s3.objects[(AUTH_PROFILE_BUCKET, key)][0]

    assert (key, loaded, b"opaque" in raw) == (
        "auth-profiles/archive-1/generation-2.json.enc",
        STATE,
        False,
    )


def new_cipher() -> AuthProfileCipher:
    return AuthProfileCipher(b"0" * 32)


def new_store(s3: FakeS3) -> AuthProfileStore:
    return EncryptedAuthProfileStore(
        s3_client=s3,
        cipher=new_cipher(),
    )
