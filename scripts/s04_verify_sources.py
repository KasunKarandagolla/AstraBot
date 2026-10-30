"""Independent CSV/native-clock audit of every S04 retained source record."""
import argparse
import csv
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import s04_economic_rescue as s


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root',type=Path,required=True)
    args=parser.parse_args()
    if ROOT==args.data_root.resolve() or ROOT in args.data_root.resolve().parents:
        raise ValueError('originals must remain outside Git')
    packet,digest=s.old.checked_json(s.OUT/'S04_EVIDENCE.json.gz',compressed=True)
    manifest=json.loads((ROOT/'research/c04/historical_manifest.json').read_text())
    by_archive={}
    for r in packet['source_bars']:
        by_archive.setdefault(r['archive_id'],{})[r['csv_record_number_including_header']]=r
    verified,partitions=0,[]
    for record in manifest['archives']:
        if record['period_utc']>='2024-10':continue
        path=args.data_root/record['data_root_relative_path']
        if sha256(path.read_bytes()).hexdigest()!=record['sha256']:raise ValueError('archive hash mismatch')
        with zipfile.ZipFile(path) as archive:
            raw=archive.read(record['members'][0])
        if sha256(raw).hexdigest()!=record['csv_member_sha256']:raise ValueError('member hash mismatch')
        expected=by_archive.pop(record['archive_id'])
        count=0
        for number,row in enumerate(csv.DictReader(io.StringIO(raw.decode())),2):
            saved=expected.pop(number)
            if saved['native_id']!=row['open_time']:raise ValueError('native ID mismatch')
            opened=datetime.fromtimestamp(int(row['open_time'])/1000,timezone.utc)
            available=datetime.fromtimestamp((int(row['close_time'])+1)/1000,timezone.utc)
            if s.dt(saved['open_time'])!=opened or s.dt(saved['available_at'])!=available:
                raise ValueError('original availability proxy mismatch')
            for source,field in (('open','open'),('high','high'),('low','low'),('close','close'),('volume','base_volume')):
                if Decimal(row[source])!=Decimal(saved[field]):raise ValueError('source value mismatch')
            count+=1
        if expected:raise ValueError('unresolved source locators')
        verified+=count
        partitions.append({'archive_id':record['archive_id'],'rows_verified':count,
                           'archive_sha256':record['sha256'],'member_sha256':record['csv_member_sha256']})
    if by_archive or verified!=266616 or len(partitions)!=84:raise ValueError('incomplete original audit')
    result={'schema_version':'s04.independent-original-csv-audit.v1','primary_evidence_content_sha256':digest,
            'audit_code_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
            'source_records_verified':verified,'archives_verified':len(partitions),
            'reserved_october_files_opened':False,'owner_arrival_proven':False,'partitions':partitions}
    result['content_sha256']=s.config_hash(result)
    (s.OUT/'S04_ORIGINAL_SOURCE_AUDIT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='partitions'},indent=2))


if __name__=='__main__':main()
