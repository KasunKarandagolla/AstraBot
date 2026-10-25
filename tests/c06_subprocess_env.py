"""Pass required OS process variables to isolated MCP test subprocesses.

Windows Python can fail while importing asyncio/_overlapped (WinError 10106)
when subprocess.run(env=...) replaces the system environment and omits SystemRoot.
Whitelist ordinary OS variables rather than forwarding unrelated secret variables.
"""
from __future__ import annotations

import os

_OS_PROCESS_KEYS = frozenset({
    "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "PATH", "PATHEXT", "COMSPEC",
    "TEMP", "TMP", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
    "APPDATA", "LOCALAPPDATA",
})


def isolated_child_environment(**overrides: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if key.upper() in _OS_PROCESS_KEYS}
    env.update(overrides)
    return env
