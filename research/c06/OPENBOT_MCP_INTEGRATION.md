# C06-C OpenBot MCP Tool Integration

**Date:** 2026-10-25
**Branch:** `codex/c06-c-openbot-mcp`
**Verified base:** `8370bc5fed417bf8e5b8cfc8b410d5c48e020601`
**SDK:** official MCP Python SDK `mcp==2.3.0`
**Scope:** stdio protocol adapter over the existing six C06 research tools.

## Compatibility status

- `MCP_PROTOCOL_INTEGRATION_TESTED`: **YES**. The SDK's `Client` launched this server as a stdio subprocess, negotiated protocol version `2026-07-28`, discovered the six tools below, and invoked them against deterministic fixtures. Structured results matched their advertised output schemas and their JSON text representation parsed successfully.
- `REAL_OPENBOT_INTEGRATION_VERIFIED`: **NOT_VERIFIED**. No OpenBot runtime was launched in this session. OpenBot's official site and changelog describe local MCP servers in Server settings and stdio subprocess launch, but that documentation and the SDK client test do not prove that an OpenBot build launches this server successfully. The host protocol version and tool invocation still require a real runtime check.

## Adapter

The entry point is `scripts/c06_mcp_server.py`. It uses the official SDK's low-level `Server` and stdio transport. The input and output JSON Schemas come directly from the existing strict C06 Pydantic models in `src/astrabot/c06/paper_mvp.py`; all requests are validated against those models before dispatch through `C06ToolGateway`.

The advertised list is exactly:

1. `scan_opportunities`
2. `evaluate_symbol`
3. `evaluate_candidates`
4. `prepare_plan`
5. `get_plan_status`
6. `get_operations_summary`

The server provides no MCP resources or prompts. `prepare_plan` can add only the existing immutable, non-executable research proposal to the process-local registry. The other tools read the deterministic fixture or that registry. The server does not expose approval, claim, submission, exchange, account, credential, filesystem, shell, or arbitrary URL tools. Unknown tools and invalid inputs return MCP tool errors without dispatching a write action.

The default fixture produces one synthetic `RESEARCH_CANDIDATE`; `--fixture no-trade` produces a synthetic `NO_TRADE` decision. Both use the existing `build_fixture` pipeline. Candidate and proposal responses retain `RESEARCH_ONLY` and `executable: false`; scan results carry `SYNTHETIC_FIXTURE`. Tool descriptions and server instructions identify fixture and research-only behavior.

## OpenBot launch configuration

The official OpenBot references document MCP server configuration in Server settings and local stdio subprocesses. In **Server settings → MCP servers**, add a local stdio server using the Python environment where this repository and its pinned dependencies are installed:

- **Command:** `/absolute/path/to/AstraBot/.venv/bin/python`
- **Arguments:** `/absolute/path/to/AstraBot/scripts/c06_mcp_server.py`
- **Working directory:** `/absolute/path/to/AstraBot`

The default process serves the positive synthetic fixture. To inspect the negative fixture during a separate manual check, append `--fixture no-trade` to the arguments. The example describes how the host should launch the process; it is not evidence that OpenBot did so. A local MCP workspace is not claimed to be an OS security boundary.

Official references consulted: [OpenBot](https://openbot.run/), [OpenBot changelog](https://openbot.run/changelog), [OpenBot source repository](https://github.com/wunitb/openbot.run), and the [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/).

## Verification

The tests use `mcp.Client` and `StdioServerParameters`, so requests cross the actual process boundary and stdio protocol. A subprocess timeout bounds the test harness at 45 seconds; each client session has a 20-second deadline, including SDK-managed shutdown. Both the client harness and MCP server subprocess block outbound socket/DNS and `urllib` calls and record any attempt. No attempt was recorded. MCP framing and response parsing would fail if non-protocol text were written to the server's stdout.

The protocol suite verifies initialization and protocol negotiation; exact six-tool discovery and strict schemas; all six tool calls; parseable typed positive outputs; the `NO_TRADE` case and plan rejection; invalid symbol, timestamp, snapshot time, candidate and plan IDs; extra numerical risk fields; deterministic proposal equality; absent approval/write tools; bounded shutdown; and no outbound network attempt.

Commands run from the repository root:

```text
/workspace/work/c06-c-venv/bin/python -m pip install -r requirements-test.txt -e .
/workspace/work/c06-c-venv/bin/python -m pytest -q tests/test_c06_mcp_protocol.py
/workspace/work/c06-c-venv/bin/python -m pytest -q
```

Results:

- MCP subprocess protocol tests: **3 passed in 6.39s**.
- Full repository suite: **220 passed in 20.12s**.
- Tool discovery: **exactly 6**, with no approval or execution tools.
- Negotiated MCP protocol: **`2026-07-28`**.
- Dependency pin: **`mcp==2.3.0`** in `pyproject.toml` and `requirements-test.txt`.

## Boundaries and remaining checks

Verified in this code and test run: the adapter is stdio-only; tool schemas are derived from the existing strict contracts; fixture decisions and proposals are research-only; the no-trade fixture cannot create a plan; malformed calls and numerical overrides fail closed; proposal output reproduces; the exposed tool list contains no exchange write action; and the exercised client/server subprocess paths made no outbound connection attempt.

Not verified: actual OpenBot process launch, OpenBot tool discovery or tool invocation; compatibility between a specific OpenBot build and the SDK's negotiated `2026-07-28` protocol; production OS/process isolation; owner authentication; durable journaling; exchange credentials or access; and any real market or strategy evidence. P3 remains `INSUFFICIENT_EVIDENCE`; the existing **45% phase credit** and **55% unqualified** accounting are unchanged. This integration does not promote strategy status, P3 evidence, or the full P4 gate.

**NEXT_GATE:** independent review of this PR. A separate real-OpenBot launch and invocation is still required before marking `REAL_OPENBOT_INTEGRATION_VERIFIED`.
