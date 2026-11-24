from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import boto3

from adapters.artifacts.auth import AuthProfileCipher, EncryptedAuthProfileStore
from adapters.browser.login import LoginBrowserSettings, PlaywrightLoginBrowser
from adapters.persistence.dynamodb.session import DynamoDBSessionStore
from application import LoginManager
from assembly import LoginSettings
from tables import LOGIN_TABLES

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.client import DynamoDBClient


class LoginRuntime:
    """Assembles the dedicated interactive-login manager and its dependencies."""

    def __init__(self, settings: LoginSettings) -> None:
        self.settings = settings
        self.browser = PlaywrightLoginBrowser(
            LoginBrowserSettings(
                display_start=settings.display_start,
                vnc_port_start=settings.vnc_port_start,
                websockify_port_start=settings.websockify_port_start,
                max_sessions=settings.max_sessions,
                novnc_root=settings.novnc_root,
            )
        )

        self.dynamodb_client: DynamoDBClient | None = None
        self.s3_client: Any | None = None
        self.manager: LoginManager | None = None
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def login_manager(self) -> LoginManager:
        if self.manager is None:
            raise RuntimeError("login runtime has not started")

        return self.manager

    async def start(self) -> None:
        if self._ready:
            raise RuntimeError("login runtime has already started")

        try:
            session = boto3.Session(
                aws_access_key_id=self.settings.aws_access_key_id,
                aws_secret_access_key=self.settings.aws_secret_access_key,
            )

            self.dynamodb_client = session.client(
                "dynamodb",
                region_name=self.settings.aws_region,
                endpoint_url=self.settings.dynamodb_endpoint_url,
            )
            self.s3_client = session.client(
                "s3",
                region_name=self.settings.aws_region,
                endpoint_url=self.settings.s3_endpoint_url,
            )

            for table_name in LOGIN_TABLES:
                await asyncio.to_thread(
                    self.dynamodb_client.describe_table,
                    TableName=table_name,
                )

            sessions = DynamoDBSessionStore(
                client=self.dynamodb_client,
                session_ttl_seconds=self.settings.session_ttl_seconds,
            )
            profiles = EncryptedAuthProfileStore(
                s3_client=self.s3_client,
                cipher=AuthProfileCipher(self.settings.auth_profile_key),
            )

            manager = LoginManager(
                sessions=sessions,
                browser=self.browser,
                profiles=profiles,
                manager_id=self.settings.manager_id,
                session_ttl_seconds=self.settings.session_ttl_seconds,
            )
            await manager.start()

            self.manager = manager
            self._ready = True
        except Exception:
            await self.stop()
            raise

    async def stop(self) -> None:
        self._ready = False
        self.manager = None

        await self.browser.close_all()

        try:
            if self.s3_client is not None:
                self.s3_client.close()
                self.s3_client = None
        finally:
            if self.dynamodb_client is not None:
                self.dynamodb_client.close()
                self.dynamodb_client = None
