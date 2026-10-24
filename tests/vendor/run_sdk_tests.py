#!/usr/bin/env python3
"""Run the 20 scoped upstream SDK tests offline.
Usage: python run_sdk_tests.py CHECKOUT_ROOT
Requires dependencies from sdk-test-requirements.lock and installed SDK metadata.
No package installation, network access, or environment/credential reads occur.
"""
import argparse
import hashlib
from importlib.metadata import version
from pathlib import Path
import socket
import sys
from unittest.mock import patch

EXPECTED = {
 'clients/derivatives_trading_usds_futures/pyproject.toml': '3cf9896c66fa3c09cd4121eefb814001fcd757e8080a467e1d3e94ee4f8cd117',
 'common/pyproject.toml': '4b144f500a6d1bf5b22b783716d0f9fff0a291f351f3626bdac01d79dd34d94b',
 'clients/derivatives_trading_usds_futures/src/binance_sdk_derivatives_trading_usds_futures/rest_api/api/trade_api.py': '0f482140acd6561cc02571110767e5c9dd363a671be0542a859536f014b1c603',
 'common/src/binance_common/utils.py': 'bbc99f348682bdc6caad65a89bf49468dd2fa96ff182d775d40479e4f1327297',
 'common/src/binance_common/websocket.py': '13de96904e3e79f35cfd7098bb5f3b4e9c6716e876b65bb247244f7a5c5b7235',
}
SELECT = ' or '.join((
 'new_order_success', 'new_algo_order_success',
 'new_order_missing_required', 'new_algo_order_missing_required',
 'test_query_algo_order_success', 'test_current_all_algo_open_orders_success',
 'test_position_information_v3_success',
 'test_reconnect_retries_until_it_succeeds',
 'test_reconnect_gives_up_after_the_configured_attempts',
 'test_reconnect_never_exceeds_the_maximum_attempts',
))

def main():
 parser=argparse.ArgumentParser();parser.add_argument('root',type=Path)
 root=parser.parse_args().root.resolve()
 for rel,digest in EXPECTED.items():
  assert hashlib.sha256((root/rel).read_bytes()).hexdigest()==digest, rel
 assert version('binance-sdk-derivatives-trading-usds-futures')=='18.1.0'
 assert version('binance-common')=='4.7.0'
 sys.path[:0]=[str(root/'common/src'),str(root/'clients/derivatives_trading_usds_futures/src')]
 # Begin blocking before loading SDK/test modules. All selected REST tests use
 # their own fake Session; this additional block makes accidental real HTTP fail.
 with patch.object(socket.socket,'connect',side_effect=AssertionError('NETWORK BLOCKED')):
  import requests
  from binance_common import utils
  import pytest
  assert Path(utils.__file__).resolve()==root/'common/src/binance_common/utils.py'
  with patch.object(requests.sessions.Session,'request',side_effect=AssertionError('HTTP BLOCKED')),patch.object(utils,'get_signature',return_value='OFFLINE_SIGNATURE_NO_CRYPTO'):
   return pytest.main([
    '-q', '--disable-warnings',
    str(root/'clients/derivatives_trading_usds_futures/tests/unit/rest_api/test_trade_api.py'),
    str(root/'common/tests/unit/test_websocket.py'),
    '-k', SELECT,
   ])

if __name__=='__main__':raise SystemExit(main())
