"""Runs one helper version once: build the output schema, wrap the data, call the gateway.
Pure of HTTP and of SQL; the service gathers the context and the flow engine (H-03) reuses this."""

import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, create_model

from recruitai.ai.gateway import LLMGateway, Part, TextPart, generate_retrying_invalid
from recruitai.ai.prompts import helper
from recruitai.core.errors import ValidationFailed
from recruitai.modules.agents.helpers.schemas import (
    EXTRA_INPUT,
    OutputSpec,
    VersionSpec,
)

MAX_TEXT = 20_000


class TextResult(BaseModel):
    text: Annotated[str, Field(max_length=MAX_TEXT)]


def fence(text: str) -> str:
    """Untrusted text must not be able to close a <data> block or open another."""
    return text.replace("<", "‹").replace(">", "›")


def output_model(spec: OutputSpec) -> type[BaseModel]:
    """One class per distinct spec, built once (a run must not rebuild it, and equal specs
    must give the same class)."""
    return _build(spec.model_dump_json())


@lru_cache(maxsize=512)
def _build(spec_json: str) -> type[BaseModel]:
    spec = OutputSpec.model_validate_json(spec_json)
    if spec.kind == "text":
        return TextResult
    fields: dict[str, Any] = {}
    for f in spec.fields:
        match f.type:
            case "text":
                t: Any = Annotated[str, Field(max_length=MAX_TEXT)]
            case "number":
                t = float
            case "boolean":
                t = bool
            case "list":
                t = Annotated[
                    list[Annotated[str, Field(max_length=2_000)]],
                    Field(max_length=50),
                ]
            case "choice":
                t = Literal[tuple(f.options)]
        fields[f.name] = (t, ...)
    return create_model("HelperResult", **fields)


def data_block(name: str, text: str) -> TextPart:
    return TextPart(f'<data name="{name}">\n{fence(text)}\n</data>')


def check_inputs(spec: VersionSpec, values: dict[str, str]) -> None:
    declared = {i.name for i in spec.inputs} | {EXTRA_INPUT}
    if extra := set(values) - declared:
        raise ValidationFailed(f"Unknown input: {min(extra)}.")
    for i in spec.inputs:
        if i.required and not values.get(i.name, "").strip():
            raise ValidationFailed(f"“{i.label}” is required.")


def clean(value: Any) -> Any:
    """Models can emit NUL, which Postgres JSONB rejects: drop it from every string."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    return value


@dataclass(frozen=True)
class Outcome:
    result: dict[str, Any]
    model: str
    latency_ms: int


async def run(
    llm: LLMGateway,
    spec: VersionSpec,
    *,
    values: dict[str, str],
    context: dict[str, str],
    feature: str,
) -> Outcome:
    """``values`` are the declared inputs, ``context`` the attached sources (name → text). A step
    sees only these two: there is nowhere else for data to come from (ADR 0031, no shared memory)."""
    check_inputs(spec, values)
    names = [i.name for i in spec.inputs]
    if EXTRA_INPUT not in names:
        names.append(
            EXTRA_INPUT
        )  # what other steps handed over beyond the declared inputs
    parts: list[Part] = [
        data_block(n, values[n]) for n in names if values.get(n, "").strip()
    ]
    parts += [data_block(name, text) for name, text in context.items()]
    parts.append(
        TextPart("Do the task in the owner instructions using the data above.")
    )
    started = time.monotonic()
    out = await generate_retrying_invalid(
        llm,
        schema=output_model(spec.output),
        system=helper.system_prompt(spec.instructions, spec.role),
        parts=parts,
        feature=feature,
        model=spec.model_tier,
    )
    return Outcome(
        result=clean(out.model_dump(mode="json")),
        model=llm.model_name(spec.model_tier, feature),
        latency_ms=int((time.monotonic() - started) * 1000),
    )
