from dataclasses import replace

import pytest

from domain.capture import StartCrawl
from domain.login import (
    AuthProfileReference,
    AuthSession,
    DuplicateSessionRequest,
    SessionConflict,
    SessionStatus,
)
from ports.capture import CrawlStarter
from ports.login import SessionStore

pytestmark = pytest.mark.integration


async def test_get_returns_the_created_session(
    session_store: SessionStore,
) -> None:
    session = AuthSession(
        session_id="session-1",
        archive_id="archive-1",
        target_url="https://example.org/login",
        status=SessionStatus.CREATED,
        expires_at="2099-01-01T00:00:00Z",
        manager_id="manager-1",
        version=1,
    )

    await session_store.create(session, "request-1", "fingerprint-1")

    assert await session_store.get("session-1") == session


async def test_get_returns_none_for_an_unknown_session(
    session_store: SessionStore,
) -> None:
    assert await session_store.get("missing") is None


async def test_find_by_request_returns_the_created_session_id(
    session_store: SessionStore,
) -> None:
    session = AuthSession(
        session_id="session-1",
        archive_id="archive-1",
        target_url="https://example.org/login",
        status=SessionStatus.CREATED,
        expires_at="2099-01-01T00:00:00Z",
        manager_id="manager-1",
        version=1,
    )

    await session_store.create(session, "request-1", "fingerprint-1")

    assert await session_store.find_by_request("request-1", "fingerprint-1") == "session-1"


async def test_find_by_request_returns_none_for_an_unknown_key(
    session_store: SessionStore,
) -> None:
    assert await session_store.find_by_request("missing", "fingerprint-1") is None


async def test_find_by_request_rejects_a_different_fingerprint(
    session_store: SessionStore,
) -> None:
    session = AuthSession(
        session_id="session-1",
        archive_id="archive-1",
        target_url="https://example.org/login",
        status=SessionStatus.CREATED,
        expires_at="2099-01-01T00:00:00Z",
        manager_id="manager-1",
        version=1,
    )

    await session_store.create(session, "request-1", "fingerprint-1")

    with pytest.raises(SessionConflict):
        await session_store.find_by_request("request-1", "fingerprint-2")


async def test_create_rejects_a_duplicate_request(
    session_store: SessionStore,
) -> None:
    session = AuthSession(
        session_id="session-1",
        archive_id="archive-1",
        target_url="https://example.org/login",
        status=SessionStatus.CREATED,
        expires_at="2099-01-01T00:00:00Z",
        manager_id="manager-1",
        version=1,
    )

    await session_store.create(session, "request-1", "fingerprint-1")

    with pytest.raises(DuplicateSessionRequest):
        session = AuthSession(
            session_id="session-1",
            archive_id="archive-1",
            target_url="https://example.org/login",
            status=SessionStatus.CREATED,
            expires_at="2099-01-01T00:00:00Z",
            manager_id="manager-1",
            version=1,
        )

    await session_store.create(session, "request-1", "fingerprint-1")


async def test_save_updates_the_session(
    session_store: SessionStore,
) -> None:
    session = AuthSession(
        session_id="session-1",
        archive_id="archive-1",
        target_url="https://example.org/login",
        status=SessionStatus.CREATED,
        expires_at="2099-01-01T00:00:00Z",
        manager_id="manager-1",
        version=1,
    )
    await session_store.create(session, "request-1", "fingerprint-1")
    updated = replace(
        session,
        status=SessionStatus.ACTIVE,
        version=2,
        vnc_origin="https://vnc.example.org",
    )

    await session_store.save(updated)

    assert await session_store.get("session-1") == updated


async def test_save_rejects_a_stale_version(
    session_store: SessionStore,
) -> None:
    session = AuthSession(
        session_id="session-1",
        archive_id="archive-1",
        target_url="https://example.org/login",
        status=SessionStatus.CREATED,
        expires_at="2099-01-01T00:00:00Z",
        manager_id="manager-1",
        version=1,
    )
    await session_store.create(session, "request-1", "fingerprint-1")
    stale = replace(session, status=SessionStatus.ACTIVE, version=3)

    with pytest.raises(SessionConflict):
        await session_store.save(stale)


async def test_reserve_generation_requires_an_archive_run(
    session_store: SessionStore,
) -> None:
    with pytest.raises(SessionConflict):
        await session_store.reserve_generation("archive-1")


async def test_reserve_generation_increments_the_generation(
    crawl_starter: CrawlStarter,
    session_store: SessionStore,
) -> None:
    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url="https://example.org/",
            max_depth=1,
            max_pages=10,
        )
    )

    assert await session_store.reserve_generation("archive-1") == 1


async def test_reserve_generation_advances_a_previous_reservation(
    crawl_starter: CrawlStarter,
    session_store: SessionStore,
) -> None:
    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url="https://example.org/",
            max_depth=1,
            max_pages=10,
        )
    )
    await session_store.reserve_generation("archive-1")

    assert await session_store.reserve_generation("archive-1") == 2


async def test_load_profile_reference_returns_none_before_a_profile_is_set(
    crawl_starter: CrawlStarter,
    session_store: SessionStore,
) -> None:
    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url="https://example.org/",
            max_depth=1,
            max_pages=10,
        )
    )

    assert await session_store.load_profile_reference("archive-1") is None


async def test_set_profile_publishes_a_profile_reference(
    crawl_starter: CrawlStarter,
    session_store: SessionStore,
) -> None:
    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url="https://example.org/",
            max_depth=1,
            max_pages=10,
        )
    )
    generation = await session_store.reserve_generation("archive-1")

    await session_store.set_profile("archive-1", generation, "profiles/profile-1.json")

    assert await session_store.load_profile_reference("archive-1") == AuthProfileReference(
        generation=1,
        key="profiles/profile-1.json",
    )


async def test_reconcile_abandoned_fails_a_session_owned_by_another_manager(
    session_store: SessionStore,
) -> None:
    session = AuthSession(
        session_id="session-1",
        archive_id="archive-1",
        target_url="https://example.org/login",
        status=SessionStatus.CREATED,
        expires_at="2099-01-01T00:00:00Z",
        manager_id="manager-1",
        version=1,
    )
    await session_store.create(session, "request-1", "fingerprint-1")

    await session_store.reconcile_abandoned("manager-2")

    assert await session_store.get("session-1") == replace(
        session,
        status=SessionStatus.FAILED,
        version=2,
        failure_reason="login manager restarted",
    )


async def test_reconcile_abandoned_keeps_an_owned_session(
    session_store: SessionStore,
) -> None:
    session = AuthSession(
        session_id="session-1",
        archive_id="archive-1",
        target_url="https://example.org/login",
        status=SessionStatus.CREATED,
        expires_at="2099-01-01T00:00:00Z",
        manager_id="manager-1",
        version=1,
    )
    await session_store.create(session, "request-1", "fingerprint-1")

    await session_store.reconcile_abandoned("manager-1")

    assert await session_store.get("session-1") == session
