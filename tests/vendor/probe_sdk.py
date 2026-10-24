#!/usr/bin/env python3
"""Offline hook into the complete pinned Binance SDK package, not extracted AST.
Usage: installed-sdk-python sdk_offline_probe.py /path/to/binance-connector-python
Install dependencies separately beforehand. No environment/credentials are read.
All HTTP and sockets are blocked; signature generation is replaced with a literal.
"""
import argparse
import hashlib
import importlib.metadata
import inspect
import json
from pathlib import Path
import socket
import sys
import tomllib
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs

EXPECTED = {
 'clients/derivatives_trading_usds_futures/pyproject.toml': '3cf9896c66fa3c09cd4121eefb814001fcd757e8080a467e1d3e94ee4f8cd117',
 'common/pyproject.toml': '4b144f500a6d1bf5b22b783716d0f9fff0a291f351f3626bdac01d79dd34d94b',
 'clients/derivatives_trading_usds_futures/src/binance_sdk_derivatives_trading_usds_futures/rest_api/api/trade_api.py': '0f482140acd6561cc02571110767e5c9dd363a671be0542a859536f014b1c603',
 'common/src/binance_common/utils.py': 'bbc99f348682bdc6caad65a89bf49468dd2fa96ff182d775d40479e4f1327297',
 'common/src/binance_common/websocket.py': '13de96904e3e79f35cfd7098bb5f3b4e9c6716e876b65bb247244f7a5c5b7235',
}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);root=parser.parse_args().root.resolve()
 for rel,digest in EXPECTED.items():
  assert hashlib.sha256((root/rel).read_bytes()).hexdigest()==digest, rel
 assert tomllib.loads((root/'clients/derivatives_trading_usds_futures/pyproject.toml').read_text())['tool']['poetry']['version']=='18.1.0'
 assert tomllib.loads((root/'common/pyproject.toml').read_text())['tool']['poetry']['version']=='4.7.0'
 assert importlib.metadata.version('binance-sdk-derivatives-trading-usds-futures')=='18.1.0'
 assert importlib.metadata.version('binance-common')=='4.7.0'
 # Import complete checkout modules. Installed metadata/dependencies are required.
 sys.path[:0]=[str(root/'common/src'),str(root/'clients/derivatives_trading_usds_futures/src')]
 with patch.object(socket.socket,'connect',side_effect=AssertionError('NETWORK BLOCKED')):
  import requests
  from binance_common.configuration import ConfigurationRestAPI
  from binance_common.errors import RequiredError,ServerError,NetworkError
  from binance_common import utils
  from binance_sdk_derivatives_trading_usds_futures.rest_api.api.trade_api import TradeApi
  from binance_sdk_derivatives_trading_usds_futures.websocket_streams.models.user_data_stream_events_response import UserDataStreamEventsResponse
  assert Path(inspect.getfile(TradeApi)).resolve()==root/'clients/derivatives_trading_usds_futures/src/binance_sdk_derivatives_trading_usds_futures/rest_api/api/trade_api.py'
  session=MagicMock(spec=requests.Session)
  response=requests.Response();response.status_code=200;response._content=b'{}';response.headers={'Content-Type':'application/json'}
  session.request.return_value=response
  config=ConfigurationRestAPI(base_path='https://offline.invalid',retries=3,backoff=0)
  api=TradeApi(configuration=config,session=session)
  checks=[]
  with patch.object(requests.sessions.Session,'request',side_effect=AssertionError('HTTP BLOCKED')),patch.object(utils,'get_signature',return_value='OFFLINE_SIGNATURE_NO_CRYPTO'):
   api.new_order(symbol='BTCUSDT',side='BUY',type='LIMIT',time_in_force='IOC',quantity='0.010',price='100.10',new_client_order_id='intent-entry-1',new_order_resp_type='RESULT')
   call=session.request.call_args.kwargs;q=parse_qs(call['params'])
   assert call['method']=='POST' and call['url'].endswith('/fapi/v1/order')
   assert q['timeInForce']==['IOC'] and q['newClientOrderId']==['intent-entry-1'] and q['price']==['100.10']
   checks.append('ordinary IOC path, client ID, decimal-string serialization')
   api.new_algo_order(algo_type='CONDITIONAL',symbol='BTCUSDT',side='SELL',type='STOP_MARKET',position_side='BOTH',trigger_price='90.00',working_type='MARK_PRICE',close_position='true',price_protect='false',client_algo_id='intent-stop-1')
   call=session.request.call_args.kwargs;q=parse_qs(call['params'])
   assert call['url'].endswith('/fapi/v1/algoOrder') and q['clientAlgoId']==['intent-stop-1']
   assert q['closePosition']==['true'] and 'quantity' not in q and 'reduceOnly' not in q
   checks.append('algo close-all path and distinct ID, omitted quantity/reduceOnly')
   # Negative evidence: SDK serializes an exchange-invalid combination.
   api.new_algo_order(algo_type='CONDITIONAL',symbol='BTCUSDT',side='SELL',type='STOP_MARKET',close_position='true',quantity=1,reduce_only='true')
   q=parse_qs(session.request.call_args.kwargs['params']);assert all(k in q for k in ('quantity','reduceOnly','closePosition'))
   checks.append('invalid close-all/quantity/reduceOnly combination passes local SDK')
   before=session.request.call_count
   try:api.new_order(symbol=None,side='BUY',type='LIMIT')
   except RequiredError:pass
   else:raise AssertionError('Missing symbol was accepted')
   assert session.request.call_count==before;checks.append('missing symbol blocked before transport')
   for method,kwargs,path,key in [
    (api.query_order,dict(symbol='BTCUSDT',orig_client_order_id='intent-entry-1'),'/fapi/v1/order','origClientOrderId'),
    (api.query_algo_order,dict(client_algo_id='intent-stop-1'),'/fapi/v1/algoOrder','clientAlgoId'),
    (api.cancel_algo_order,dict(client_algo_id='intent-stop-1'),'/fapi/v1/algoOrder','clientAlgoId'),
    (api.current_all_open_orders,dict(symbol='BTCUSDT'),'/fapi/v1/openOrders','symbol'),
    (api.current_all_algo_open_orders,dict(symbol='BTCUSDT'),'/fapi/v1/openAlgoOrders','symbol'),
    (api.position_information_v3,dict(symbol='BTCUSDT'),'/fapi/v3/positionRisk','symbol')]:
    method(**kwargs);call=session.request.call_args.kwargs;assert call['url'].endswith(path) and key in parse_qs(call['params'])
   checks.append('ordinary/algo query, algo cancel, both open-order lists, v3 position routes')
   session.request.reset_mock();session.request.side_effect=requests.Timeout('offline timeout')
   try:api.new_order(symbol='BTCUSDT',side='BUY',type='LIMIT',time_in_force='IOC',quantity=1,price=100)
   except NetworkError as exc:assert isinstance(exc.__cause__,requests.Timeout)
   else:raise AssertionError('timeout swallowed')
   assert session.request.call_count==1;checks.append('IOC POST timeout wraps NetworkError with one transport attempt')
   session.request.reset_mock();session.request.side_effect=None;response.status_code=503;response._content=b'{"msg":"Unknown error, please check your request or try again later."}'
   try:api.new_order(symbol='BTCUSDT',side='BUY',type='LIMIT',time_in_force='IOC',quantity=1,price=100)
   except ServerError as exc:assert exc.status_code==503
   else:raise AssertionError('503 swallowed')
   assert session.request.call_count==1;checks.append('IOC POST unknown 503 yields generic ServerError, no retry')
  for name in ('ORDER_TRADE_UPDATE','ACCOUNT_UPDATE','ALGO_UPDATE','listenKeyExpired'):
   ev=UserDataStreamEventsResponse.from_dict({'e':name,'E':1,'T':1})
   assert type(ev.actual_instance).__name__ in ('OrderTradeUpdate','AccountUpdate','AlgoUpdate','ListenKeyExpired')
  checks.append('four user-data e-field model routes')
 print(json.dumps({'status':'FAKE_TESTED','scope':'actual full checkout package, mocked transport/signature; no exchange evidence','versions':{'sdk':'18.1.0','common':'4.7.0'},'checks':checks,'count':len(checks)},indent=2))

if __name__=='__main__':main()
