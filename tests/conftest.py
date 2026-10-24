"""All normal tests run without exchange credentials and with sockets disabled."""
import os
import socket
import pytest


@pytest.fixture(autouse=True)
def deny_network_and_credentials(monkeypatch):
    for name in tuple(os.environ):
        if any(part in name.upper() for part in ("BINANCE", "API_KEY", "API_SECRET", "TOKEN", "CREDENTIAL")):
            monkeypatch.delenv(name, raising=False)
    def denied(*args, **kwargs):
        raise AssertionError("C01 fake tests prohibit all network sockets")
    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
