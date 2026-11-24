from typing import Any

from domain import ArchivePage, AuthSession, PageListing, SnapshotReference


def archive_page_json(page: ArchivePage) -> dict[str, Any]:
    result: dict[str, Any] = {"url": page.url, "status": page.status}

    if page.snapshot_id is not None:
        result["snapshotId"] = page.snapshot_id

    if page.error_code is not None:
        result["errorCode"] = page.error_code

    if page.captured_at is not None:
        result["capturedAt"] = page.captured_at

    return result


def page_listing_json(listing: PageListing) -> dict[str, Any]:
    result: dict[str, Any] = {
        "items": [archive_page_json(item) for item in listing.items],
    }

    if listing.next_cursor is not None:
        result["nextCursor"] = listing.next_cursor

    return result


def snapshot_reference_json(snapshot: SnapshotReference) -> dict[str, Any]:
    result: dict[str, Any] = {
        "archiveId": snapshot.archive_id,
        "snapshotId": snapshot.snapshot_id,
        "url": snapshot.url,
        "capturedAt": snapshot.captured_at,
    }

    if snapshot.final_url:
        result["finalUrl"] = snapshot.final_url

    if snapshot.content_type is not None:
        result["contentType"] = snapshot.content_type

    return result


def auth_session_json(session: AuthSession) -> dict[str, Any]:
    result: dict[str, Any] = {
        "sessionId": session.session_id,
        "archiveId": session.archive_id,
        "status": str(session.status),
        "expiresAt": session.expires_at,
    }

    if session.auth_generation is not None:
        result["authGeneration"] = session.auth_generation

    return result
