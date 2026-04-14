"""Shared agent execution utilities: retry loop + validation error tracking.

Usage inside an agent
---------------------
    from app.agents._agent_utils import validate_or_retry, AgentValidationError

    async def funnel_agent(state: dict) -> dict:
        async def _run(s: dict) -> tuple[dict, list[str]]:
            result = _compute(s)
            errors = _validate_funnel(result)
            return result, errors

        metrics, validation_errors = await validate_or_retry(
            run_fn=_run,
            state=state,
            agent_name="funnel_agent",
            state_key="funnel_metrics",
        )
        return {"funnel_metrics": metrics, **_error_patch("funnel_agent", validation_errors)}

Contract
--------
- ``run_fn(state) -> (result_dict, errors: list[str])``
  * ``errors`` is an empty list when the result is acceptable.
  * ``errors`` contains human-readable strings when something is wrong.
- If errors remain after MAX_RETRIES the last result is returned anyway and
  all errors are recorded so the pipeline can continue.
- Every attempt, success, and failure is logged with the agent name and
  attempt number so log grep / tracing is unambiguous.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


class AgentValidationError(Exception):
    """Raised when an agent's output fails business-logic validation on all retries."""

    def __init__(self, agent_name: str, errors: list[str]) -> None:
        self.agent_name = agent_name
        self.errors = errors
        super().__init__(f"{agent_name}: validation failed after {MAX_RETRIES} attempts — {errors}")


async def validate_or_retry(
    run_fn: Callable[[dict], Awaitable[tuple[dict, list[str]]]],
    state: dict,
    agent_name: str,
    state_key: str,
) -> tuple[dict, list[str]]:
    """Run ``run_fn`` up to MAX_RETRIES times until it returns no errors.

    Parameters
    ----------
    run_fn:
        Async callable ``(state) -> (result, errors)``.
        ``errors`` is ``[]`` on success, or a list of strings describing what
        is wrong with the result.
    state:
        Current pipeline state dict (passed through to run_fn unchanged).
    agent_name:
        Used in log messages (e.g. "funnel_agent").
    state_key:
        The PipelineState key this agent writes (e.g. "funnel_metrics").
        Used in log messages only.

    Returns
    -------
    (result, errors)
        The last computed result and the final list of errors (empty on success).
    """
    last_result: dict = {}
    last_errors: list[str] = []

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result, errors = await run_fn(state)
        except Exception as exc:  # noqa: BLE001
            last_errors = [f"unexpected exception: {exc}"]
            last_result = {}
            logger.error(
                "%s [attempt %d/%d] raised an exception: %s",
                agent_name, attempt, MAX_RETRIES, exc,
                exc_info=True,
            )
            if attempt < MAX_RETRIES:
                logger.info("%s retrying (attempt %d → %d)…", agent_name, attempt, attempt + 1)
            continue

        if not errors:
            if attempt > 1:
                logger.info(
                    "%s [attempt %d/%d] validation passed for '%s'",
                    agent_name, attempt, MAX_RETRIES, state_key,
                )
            return result, []

        last_result = result
        last_errors = errors
        logger.warning(
            "%s [attempt %d/%d] validation failed for '%s': %s",
            agent_name, attempt, MAX_RETRIES, state_key, errors,
        )
        if attempt < MAX_RETRIES:
            logger.info("%s retrying (attempt %d → %d)…", agent_name, attempt, attempt + 1)

    logger.error(
        "%s exhausted %d retries for '%s'. Returning last result with errors: %s",
        agent_name, MAX_RETRIES, state_key, last_errors,
    )
    return last_result, last_errors


def error_patch(agent_name: str, errors: list[str]) -> dict[str, Any]:
    """Return a state fragment recording validation errors for this agent.

    The pipeline state will contain ``validation_errors`` as a dict keyed by
    agent name so downstream nodes (and operators) can inspect what went wrong.

    Example
    -------
        return {"funnel_metrics": metrics, **error_patch("funnel_agent", errors)}

    In state this produces::

        {
            "funnel_metrics": {...},
            "validation_errors": {"funnel_agent": ["첫 단계 user_count == 0"]},
        }
    """
    if not errors:
        return {}
    return {"validation_errors": {agent_name: errors}}
