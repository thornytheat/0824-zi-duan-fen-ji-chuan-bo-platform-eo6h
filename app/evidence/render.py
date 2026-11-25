import json


def artifact(run, revocations=None):
    packet = {
        'schema': 'review-evidence/1',
        'manifest': run['report']['manifest'],
        'balance': run['report']['balance'],
        'cases': run['report']['cases'],
        'intake': run['report']['intake'],
        'revocations': revocations if revocations is not None else run.get('revocations', []),
        'review': {key:run[key] for key in ('status','revision','note','reviewed')},
    }
    return (json.dumps(packet, ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
