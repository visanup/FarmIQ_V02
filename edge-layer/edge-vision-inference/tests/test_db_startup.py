"""Startup recovery tests; also runnable with standard-library unittest."""
import asyncio
import socket
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.db import InferenceDb


class DatabaseStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_failures_recover(self):
        class CannotConnectNowError(Exception):
            pass

        pool = object()
        create_pool = AsyncMock(side_effect=[
            socket.gaierror(-3, "Temporary failure in name resolution"),
            CannotConnectNowError("database system is starting up"),
            asyncio.TimeoutError(),
            pool,
        ])
        driver = SimpleNamespace(create_pool=create_pool, exceptions=SimpleNamespace(
            CannotConnectNowError=CannotConnectNowError))
        with patch("app.db.asyncpg", driver), patch("app.db.asyncio.sleep", new_callable=AsyncMock) as sleep:
            db = InferenceDb("postgresql://unused")
            await db.connect()
        self.assertIs(db.pool, pool)
        self.assertEqual([call.args[0] for call in sleep.await_args_list], [1, 2, 4])
        self.assertEqual(create_pool.call_args.kwargs["timeout"], 10)

    async def test_persistent_failure_exits_after_bounded_retries(self):
        create_pool = AsyncMock(side_effect=ConnectionRefusedError("unavailable"))
        driver = SimpleNamespace(create_pool=create_pool, exceptions=SimpleNamespace(
            CannotConnectNowError=type("CannotConnectNowError", (Exception,), {})))
        with patch("app.db.asyncpg", driver), patch("app.db.asyncio.sleep", new_callable=AsyncMock) as sleep:
            db = InferenceDb("postgresql://unused")
            with self.assertRaises(ConnectionRefusedError):
                await db.connect()
        self.assertIsNone(db.pool)
        self.assertEqual(create_pool.await_count, 8)
        self.assertEqual([call.args[0] for call in sleep.await_args_list], [1, 2, 4, 8, 10, 10, 10])

    async def test_configuration_error_is_not_retried(self):
        create_pool = AsyncMock(side_effect=ValueError("invalid connection configuration"))
        driver = SimpleNamespace(create_pool=create_pool, exceptions=SimpleNamespace(
            CannotConnectNowError=type("CannotConnectNowError", (Exception,), {})))
        with patch("app.db.asyncpg", driver), patch("app.db.asyncio.sleep", new_callable=AsyncMock) as sleep:
            with self.assertRaises(ValueError):
                await InferenceDb("invalid").connect()
        self.assertEqual(create_pool.await_count, 1)
        sleep.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
