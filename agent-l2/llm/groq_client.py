"""Async Groq client with forced tool-calling and Pydantic validation.

Every structured LLM call in Layer 2 goes through :func:`call_structured`:
the model is forced to call one tool whose JSON schema is generated from a
Pydantic model; the arguments are validated, and on failure the error is fed
back to the model so it can self-repair (up to ``max_attempts``).
"""
import json
import os
from typing import Any, Callable, TypeVar

from groq import AsyncGroq, AuthenticationError, BadRequestError, PermissionDeniedError
from pydantic import BaseModel

from llm.trace import make_event, now

T = TypeVar("T", bound=BaseModel)


class LLMConfigError(Exception):
    """Missing/invalid credentials. Non-retryable (see workflow retry policy)."""


class LLMOutputError(Exception):
    """The model could not produce valid structured output within the attempt budget."""


_client: AsyncGroq | None = None


def get_client() -> AsyncGroq:
    """Return a cached :class:`groq.AsyncGroq` client."""
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise LLMConfigError("GROQ_API_KEY is not set")
        _client = AsyncGroq(api_key=api_key, max_retries=4, timeout=90.0)
    return _client


def tool_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Return a self-contained JSON schema (``$ref``s inlined) for a Pydantic model."""
    schema = model.model_json_schema()
    defs: dict[str, Any] = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(schema)


async def call_structured(
    *,
    model: str,
    system: str,
    user: str,
    schema: type[T],
    tool_name: str,
    tool_description: str,
    run_id: str,
    node: str,
    events: list[dict[str, Any]],
    max_tokens: int = 2048,
    temperature: float = 0.1,
    max_attempts: int = 3,
    validator: Callable[[T], None] | None = None,
) -> T:
    """Call Groq, force ``tool_name`` and return a validated ``schema`` instance.

    Args:
        validator: optional semantic check; raise ``ValueError`` to send the
            message back to the model as repair feedback.
        events: a trace event is appended here (tokens, latency, attempts).

    Raises:
        LLMConfigError: credentials missing or rejected.
        LLMOutputError: no valid output after ``max_attempts``.
    """
    client = get_client()
    tool = {
        "type": "function",
        "function": {"name": tool_name, "description": tool_description, "parameters": tool_schema(schema)},
    }
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    started = now()
    prompt_tokens = completion_tokens = 0
    last_error = "unknown error"

    for attempt in range(1, max_attempts + 1):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                tools=[tool],  # type: ignore[list-item]
                tool_choice={"type": "function", "function": {"name": tool_name}},
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except (AuthenticationError, PermissionDeniedError) as exc:
            events.append(make_event(node=node, run_id=run_id, started_at=started, status="failed",
                                     event_type="llm_call", model=model, attempts=attempt, error="auth error"))
            raise LLMConfigError(f"Groq rejected the API key: {exc}") from exc
        except BadRequestError as exc:  # includes Groq "tool_use_failed" (malformed generation)
            last_error = f"provider rejected generation: {str(exc)[:300]}"
            messages.append({"role": "user", "content": "Your last tool call was malformed. "
                             "Call the tool again with valid JSON that matches the schema exactly."})
            continue

        if response.usage:
            prompt_tokens += response.usage.prompt_tokens or 0
            completion_tokens += response.usage.completion_tokens or 0
        message = response.choices[0].message
        if not message.tool_calls:
            last_error = "model did not call the tool"
            messages.append({"role": "user", "content": f"You must call the tool {tool_name}."})
            continue

        call = message.tool_calls[0]
        try:
            parsed = schema.model_validate(json.loads(call.function.arguments))
            if validator is not None:
                validator(parsed)
        except ValueError as exc:  # JSONDecodeError, pydantic ValidationError and validator errors
            last_error = str(exc)[:1500]
            messages.append({"role": "assistant", "content": None, "tool_calls": [{
                "id": call.id, "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments}}]})
            messages.append({"role": "tool", "tool_call_id": call.id,
                             "content": f"ERROR: {last_error}\nFix the problems and call the tool again."})
            continue

        events.append(make_event(node=node, run_id=run_id, started_at=started, event_type="llm_call",
                                 model=model, prompt_tokens=prompt_tokens,
                                 completion_tokens=completion_tokens, attempts=attempt))
        return parsed

    events.append(make_event(node=node, run_id=run_id, started_at=started, status="failed",
                             event_type="llm_call", model=model, prompt_tokens=prompt_tokens,
                             completion_tokens=completion_tokens, attempts=max_attempts, error=last_error[:500]))
    raise LLMOutputError(f"{node}: no valid output after {max_attempts} attempts: {last_error}")
