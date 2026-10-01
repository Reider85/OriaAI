"""Regression guard for runtime dependencies that are only exercised in Docker.

Background: agent-service runs ``alembic upgrade head`` on every container start,
and ``migrations/env.py`` imports ``sqlalchemy.ext.asyncio``, which requires the
``greenlet`` package. ``pyproject.toml`` originally declared plain
``sqlalchemy>=2.0.0``, so a fresh container never got ``greenlet`` and the
service died on startup -- then restart-looped forever, because
``restart: unless-stopped`` re-ran the same broken command.

A developer virtualenv hides this: ``greenlet`` is commonly pulled in
transitively by another dependency, so the suite passes locally while the
container is broken. The assertion below therefore targets the declared
metadata in ``pyproject.toml`` (the source of truth a fresh install reads)
rather than the ambient environment.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
PYPROJECT = ROOT / "pyproject.toml"
ALEMBIC_ENV = ROOT / "migrations" / "env.py"


def _declared_dependencies() -> list[str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return list(data["project"]["dependencies"])


_REQUIREMENT_NAME = re.compile(r"^[A-Za-z0-9._-]+")


def _requirement_for(package: str) -> str | None:
    """Return the requirement string declaring ``package`` (PEP 508 name match)."""
    for requirement in _declared_dependencies():
        match = _REQUIREMENT_NAME.match(requirement.strip())
        if match is not None and match.group(0).lower() == package:
            return requirement
    return None


class TestSqlalchemyAsyncExtra:
    def test_pyproject_declares_asyncio_extra(self):
        requirement = _requirement_for("sqlalchemy")
        assert requirement is not None, "sqlalchemy must stay a declared dependency"
        assert "[asyncio]" in requirement, (
            f"expected 'sqlalchemy[asyncio]' in {requirement!r}: the [asyncio] extra "
            "pulls in greenlet, which migrations/env.py needs via "
            "sqlalchemy.ext.asyncio. Without it a fresh container install omits "
            "greenlet and agent-service restart-loops on 'alembic upgrade head'."
        )

    def test_alembic_env_actually_needs_asyncio(self):
        """Justifies the extra: drop this coupling if env.py stops using async."""
        source = ALEMBIC_ENV.read_text(encoding="utf-8")
        assert "sqlalchemy.ext.asyncio" in source, (
            "this test assumes migrations/env.py imports sqlalchemy.ext.asyncio"
        )

    def test_greenlet_importable_in_current_env(self):
        """Runtime sanity check; the metadata assertion above is the real guard."""
        greenlet = pytest.importorskip(
            "greenlet",
            reason="greenlet absent locally, which is exactly the container bug",
        )
        assert greenlet.__version__


class TestComposeAgentService:
    def test_agent_install_is_retryable_and_cached(self):
        """A cold install downloads ~800MB; retries/cache keep startup survivable."""
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        service = compose.split("agent-service:", 1)[1]
        install = service.split("command:", 1)[1].split("healthcheck:", 1)[0]
        assert "pip install" in install
        assert "--retries" in install
        assert "agent-pip-cache:/root/.cache/pip" in service
