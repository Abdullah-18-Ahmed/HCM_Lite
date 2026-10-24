"""T044: live smoke against the real OpenAI service (``pytest -m live``).

Skipped cleanly when ``OPENAI_API_KEY`` is not configured. Verifies that both configured
models are available to the key (``config.verify_models``) and that one real agent turn
returns non-empty text with no error category.
"""

from __future__ import annotations

from datetime import date

import pytest

pytestmark = pytest.mark.live


def _live_settings():
    """Real settings from ``.env`` / the environment; skip when the API key is absent."""
    from hcm_lite.config import load_settings
    from hcm_lite.errors import ConfigurationError

    try:
        return load_settings()
    except ConfigurationError as exc:
        if "OPENAI_API_KEY" in exc.variables:
            pytest.skip("OPENAI_API_KEY is not set")
        raise


async def test_verify_models_passes():
    from hcm_lite.config import verify_models

    await verify_models(_live_settings())


async def test_run_turn_returns_non_empty_text():
    from hcm_lite.assistant.context import AppContext, AppSession, Services
    from hcm_lite.assistant.hr_agent import build_agent, production_run_config
    from hcm_lite.assistant.runner import run_turn
    from hcm_lite.assistant.tools import TOOLS
    from hcm_lite.models.domain import AuthenticatedUser, Role

    settings = _live_settings()
    user = AuthenticatedUser(user_id="live-smoke", username="live-smoke", role=Role.EMPLOYEE,
                             employee_id="E0", display_name="Live Smoke", department="QA")
    services = Services(agent=build_agent(settings, TOOLS),
                        run_config=production_run_config(),  # tracing disabled (F6)
                        max_turns=settings.agent_max_turns)
    ctx = AppContext(user=user, session=AppSession(user=user), today=date.today(),
                     services=services)
    result = await run_turn(ctx, "Reply with exactly one word: ready")
    assert result.error_category is None, result.error_category
    assert result.final_text.strip()
