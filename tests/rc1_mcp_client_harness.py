"""Real stdio MCP check kept outside pytest's all-sockets-denied parent."""
import asyncio
import json
from pathlib import Path
import sys
from mcp import Client, StdioServerParameters
from astrabot.c06.paper_mvp import C06ToolGateway
from c06_subprocess_env import isolated_child_environment

ROOT = Path(__file__).resolve().parents[1]
snapshot = Path(sys.argv[1])
payload = json.loads(snapshot.read_text())
at = payload['as_of']
async def check():
    params = StdioServerParameters(command=sys.executable,
        args=[str(ROOT/'scripts/c06_mcp_server.py'), '--research-snapshot', str(snapshot)],
        cwd=str(ROOT), env=isolated_child_environment())
    async with Client(params, read_timeout_seconds=15) as client:
        assert tuple(t.name for t in (await client.list_tools()).tools) == C06ToolGateway.tool_names
        scan = await client.call_tool('scan_opportunities', {'as_of': at})
        assert scan.structured_content['fixture_label'] == 'OBSERVED_HISTORICAL_RESEARCH'
        decision = await client.call_tool('evaluate_symbol', {'symbol':'BTCUSDT', 'as_of':at})
        ids = decision.structured_content['decision_ids']
        assert set(decision.structured_content['research_decisions']) == {'NO_TRADE'}
        assert (await client.call_tool('prepare_plan', {'candidate_id':ids[0]})).is_error
        assert (await client.call_tool('prepare_plan', {'candidate_id':ids[0], 'risk_override_usdt':1000})).is_error
        journal = await client.call_tool('get_operations_summary', {})
        return journal.structured_content
first = asyncio.run(check())
assert first['event_count'] == len(payload['journal_events']) > 0
assert asyncio.run(check()) == first
print("RC1_HISTORICAL_MCP_PASS")
