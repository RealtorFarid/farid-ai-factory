"""A deterministic offline model, for local verification only.

``PROPILOT_DEFAULT_MODEL=stub`` runs the whole product — streaming, tools, the
approval gate — with no provider, no key and no cost.

This exists because PydanticAI's built-in ``TestModel`` fabricates the string
``'a'`` for every parameter, which is useless for exercising the approval flow:
the arguments refer to nothing real, so nothing observable happens when a call
is approved. This stub proposes one ungated read and two gated actions against
seeded records, which is exactly the shape needed to demonstrate approving one
action and denying another.

Never selected in production: ``resolve_model`` only returns it for the literal
model name ``stub``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

__all__ = ["STUB_MODEL_NAME", "build_stub_extraction_model", "build_stub_model"]

STUB_MODEL_NAME = "stub"

_SUMMARY = (
    "Here is where today stands.\n\n"
    "Dana Okafor's financing condition is the most urgent item — the offer on "
    "42 Maple Grove is your largest open deal. Priya Raman replied within the "
    "hour and is ready for a second showing.\n\n"
    "I proposed two actions above: a reply to Priya confirming Thursday, and "
    "closing out the follow-up task once that is sent. Neither runs until you "
    "approve it."
)


def _tool_has_reported_back(messages: list[ModelMessage]) -> bool:
    """True once any tool produced a result — approved, denied or errored."""
    return any(
        getattr(part, "part_kind", None) in ("tool-return", "retry-prompt")
        for message in messages
        for part in getattr(message, "parts", [])
    )


def _last_user_text(messages: list[ModelMessage]) -> str:
    for message in reversed(messages):
        for part in getattr(message, "parts", []):
            if getattr(part, "part_kind", None) == "user-prompt":
                content = getattr(part, "content", "")
                if isinstance(content, str):
                    return content
    return ""


def build_stub_extraction_model() -> FunctionModel:
    """Offline extractor that quotes the note, so grounding is exercised."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        note = _last_user_text(messages)
        sentences = [s.strip() for s in note.replace("\n", " ").split(".") if s.strip()]
        claims = [
            {
                "predicate": f"note_detail_{index + 1}",
                "value": sentence[:200],
                "confidence": 0.7,
                # Quoting verbatim is what lets the grounding check pass.
                "quote": sentence,
                "volatile": False,
            }
            for index, sentence in enumerate(sentences[:3])
        ]
        payload = {
            "summary": (sentences[0][:200] if sentences else "Empty note."),
            "claims": claims,
            "follow_ups": ["Confirm the details captured above."] if claims else [],
        }
        tool_name = info.output_tools[0].name if info.output_tools else "final_result"
        return ModelResponse(parts=[ToolCallPart(tool_name, json.dumps(payload))])

    return FunctionModel(respond, model_name=f"{STUB_MODEL_NAME}-extractor")


def build_stub_model() -> FunctionModel:
    """A model that reads the workspace, then proposes two gated actions."""

    async def stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        if _tool_has_reported_back(messages):
            # Stream the answer in chunks so the UI's token rendering is
            # exercised rather than bypassed.
            for chunk in _SUMMARY.split(" "):
                yield f"{chunk} "
            return

        yield {
            # Ungated: runs immediately, proving tool.called -> tool.executed.
            0: DeltaToolCall(name="summarize_leads", json_args="{}"),
            # Gated: both pause for approval.
            1: DeltaToolCall(
                name="send_email",
                json_args=json.dumps(
                    {
                        "lead_id": "lead_001",
                        "subject": "Thursday 6pm at 155 Yonge St",
                        "body": (
                            "Hi Priya — confirming Thursday at 6pm for the "
                            "2-bed at 155 Yonge St. The unit is still "
                            "available. Reply here if the time shifts."
                        ),
                    }
                ),
            ),
            2: DeltaToolCall(
                name="complete_task",
                json_args=json.dumps({"task_id": "tsk_001"}),
            ),
        }

    return FunctionModel(stream_function=stream, model_name=STUB_MODEL_NAME)
