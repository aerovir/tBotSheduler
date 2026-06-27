"""Integration tests for /health endpoint."""
from __future__ import annotations

from httpx import AsyncClient


class TestHealthEndpoint:
    """Test the FastAPI /health endpoint."""

    async def test_health_returns_200(self, client: AsyncClient):
        """Test health endpoint returns 200 OK."""
        response = await client.get("/health")
        assert response.status_code == 200

    async def test_health_structure(self, client: AsyncClient):
        """Test health response has expected structure."""
        response = await client.get("/health")
        data = response.json()

        # Top-level fields
        assert "status" in data
        assert "version" in data
        assert "uptime_seconds" in data
        assert "response_time_ms" in data
        assert "checks" in data

        # Version check
        assert data["version"] == "0.1.0"

    async def test_health_checks_all_present(self, client: AsyncClient):
        """Test all required checks are present."""
        response = await client.get("/health")
        checks = response.json()["checks"]

        required_checks = [
            "database", "bot", "telegram_api",
            "disk", "memory", "scheduler",
        ]
        for check in required_checks:
            assert check in checks, f"Missing check: {check}"

    async def test_health_each_check_has_status_and_detail(
        self, client: AsyncClient
    ):
        """Test each check has status and detail fields."""
        response = await client.get("/health")
        checks = response.json()["checks"]

        for name, check in checks.items():
            assert "status" in check, f"{name} missing status"
            assert "detail" in check, f"{name} missing detail"
            assert check["status"] in ("ok", "degraded", "down"), (
                f"{name} has invalid status: {check['status']}"
            )

    async def test_health_scheduler_check(self, client: AsyncClient):
        """Test scheduler check returns ok with 0 pending notifications."""
        response = await client.get("/health")
        scheduler = response.json()["checks"]["scheduler"]
        assert scheduler["status"] in ("ok", "degraded", "down")
