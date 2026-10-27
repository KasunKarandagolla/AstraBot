#!/usr/bin/env python3
"""Six offline research/proposal tools over synthetic or sealed historical inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import anyio
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from astrabot.c06.paper_mvp import (
    C06ToolGateway,
    CandidateOutput,
    EvaluateCandidatesInput,
    EvaluateSymbolInput,
    EvaluateSymbolOutput,
    GetOperationsSummaryInput,
    GetPlanStatusInput,
    OperationsSummaryOutput,
    PaperPlan,
    PlanStatusOutput,
    PreparePlanInput,
    ScanOpportunitiesInput,
    ScanOpportunitiesOutput,
)
from c06_paper_demo import build_fixture
from c06_fixture_paths import prepare_synthetic_state_dir


TOOL_MODELS: dict[str, tuple[type[BaseModel], type[BaseModel], str]] = {
    "scan_opportunities": (
        ScanOpportunitiesInput,
        ScanOpportunitiesOutput,
        "Scan the fixed offline snapshot. Inspect its evidence label; research only.",
    ),
    "evaluate_symbol": (
        EvaluateSymbolInput,
        EvaluateSymbolOutput,
        "Evaluate the selected offline symbol at its frozen snapshot time. Output is research-only.",
    ),
    "evaluate_candidates": (
        EvaluateCandidatesInput,
        CandidateOutput,
        "Return the selected offline decision for supplied IDs; unknown or rejected IDs yield NO_TRADE.",
    ),
    "prepare_plan": (
        PreparePlanInput,
        PaperPlan,
        "Create an immutable, synthetic, non-executable research proposal from the fixture candidate.",
    ),
    "get_plan_status": (
        GetPlanStatusInput,
        PlanStatusOutput,
        "Read verified fixture proposal status; no approval or execution occurs.",
    ),
    "get_operations_summary": (
        GetOperationsSummaryInput,
        OperationsSummaryOutput,
        "Summarize verified offline machine events. Inspect scan_opportunities for their evidence class.",
    ),
}


def _tool_definitions() -> list[Tool]:
    return [
        Tool(
            name=name,
            description=description,
            input_schema=input_model.model_json_schema(),
            output_schema=output_model.model_json_schema(),
            annotations={
                "readOnlyHint": name != "prepare_plan",
                "destructiveHint": False,
                "openWorldHint": False,
            },
        )
        for name, (input_model, output_model, description) in TOOL_MODELS.items()
    ]


def _validation_message(error: ValidationError) -> str:
    parts = []
    for item in error.errors(include_url=False):
        location = ".".join(str(piece) for piece in item["loc"]) or "input"
        parts.append(f"{location}: {item['msg']}")
    return "; ".join(parts)


def _error(message: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=message)],
        is_error=True,
    )


def create_server(gateway: C06ToolGateway) -> Server:
    definitions = _tool_definitions()

    async def list_tools(
        _ctx: ServerRequestContext,
        _params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        return ListToolsResult(tools=definitions)

    async def call_tool(
        _ctx: ServerRequestContext,
        params: CallToolRequestParams,
    ) -> CallToolResult:
        name = params.name
        contract = TOOL_MODELS.get(name)
        if contract is None:
            return _error(f"Unknown C06 tool: {name}")

        input_model, output_model, _description = contract
        arguments = params.arguments or {}
        try:
            # JSON-mode validation preserves strict Pydantic input semantics while
            # parsing JSON datetimes and arrays into their declared Python types.
            request = input_model.model_validate_json(
                json.dumps(arguments, separators=(",", ":"), allow_nan=False)
            )
            response = gateway.call(name, request.model_dump(mode="python"))
            if not isinstance(response, output_model):
                return _error(f"{name} returned an unexpected response type")
            payload = response.model_dump(mode="json")
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        except ValidationError as error:
            return _error(f"Invalid input for {name}: {_validation_message(error)}")
        except KeyError:
            return _error("Unknown plan ID")
        except (ValueError, TypeError) as error:
            # Gateway errors contain fixed domain explanations. Avoid reflecting
            # caller-supplied values in the protocol error response.
            return _error(f"Request rejected by {name}: {error}")

        return CallToolResult(
            content=[TextContent(type="text", text=encoded)],
            structured_content=payload,
            is_error=False,
        )

    return Server(
        "AstraBot C06 Offline MCP",
        version="0.1.0",
        instructions=(
            "Tools use one deterministic offline snapshot; inspect its evidence class. "
            "No tool approves, claims, submits, places, or manages exchange orders. "
            "This local MCP process is not an OS security boundary."
        ),
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def _serve(gateway: C06ToolGateway) -> None:
    server = create_server(gateway)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        choices=("positive", "no-trade"),
        default="positive",
        help="Select one deterministic offline fixture; never connects to an exchange.",
    )
    parser.add_argument("--state-dir", type=Path,
        help="opt in to a dedicated persistent synthetic-only fixture directory")
    parser.add_argument("--research-snapshot", type=Path,
        help="sealed authentic snapshot exported by c05_integrated_research --mode authentic")
    args = parser.parse_args(argv)
    if args.research_snapshot:
        if args.state_dir is not None or '--fixture' in (argv if argv is not None else sys.argv[1:]):
            parser.error("historical snapshots cannot be combined with synthetic fixture/state options")
        from astrabot.c06.research_operator import load_operator_gateway
        anyio.run(_serve, load_operator_gateway(args.research_snapshot))
        return
    state_path = None
    if args.state_dir is not None:
        state_dir = prepare_synthetic_state_dir(args.state_dir)
        state_path = state_dir / "c06_state.sqlite"
    fixture = build_fixture(event_evidence=args.fixture != "no-trade",
        storage_path=state_path)
    anyio.run(_serve, fixture["gateway"])


if __name__ == "__main__":
    main()
