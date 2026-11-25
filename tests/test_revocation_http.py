import io

from test_revocation import approval_batch, cases_of


def _run(client):
    response = client.post('/api/runs', data={'file': (io.BytesIO(approval_batch()), 'input.csv')})
    assert response.status_code == 200
    return response.json['id']


def test_revocation_endpoint_suspends_group(client):
    run_id = _run(client)
    client.patch(f'/api/runs/{run_id}', json=dict(revision=0, status='APPROVED', note='批次签发'))
    response = client.post(f'/api/runs/{run_id}/revocations',
                           json=dict(case='A', field=2, day=8, note='审批撤销'))
    assert response.status_code == 200
    body = response.json
    assert body['status'] == 'SUSPENDED'
    assert cases_of(body)['A']['status'] == 'SUPPLY_SUSPENDED'


def test_revocation_list_endpoint(client):
    run_id = _run(client)
    response = client.post(f'/api/runs/{run_id}/revocations',
                           json=dict(case='A', field=2, day=8, note='审批撤销'))
    assert response.status_code == 200
    listing = client.get(f'/api/runs/{run_id}/revocations')
    assert listing.status_code == 200
    items = listing.json['items']
    assert items == [dict(case='A', field=2, day=8, label=None)]


def test_early_revocation_returns_conflict(client):
    run_id = _run(client)
    response = client.post(f'/api/runs/{run_id}/revocations',
                           json=dict(case='A', field=2, day=5, note='过早的撤销'))
    assert response.status_code == 409
    assert response.json['code'] == 'REVOKED_BEFORE_VERIFICATION'


def test_revocation_unknown_run_returns_404(client):
    response = client.post('/api/runs/unknown/revocations',
                           json=dict(case='A', field=2, day=8, note='审批撤销'))
    assert response.status_code == 404


def test_revocation_bad_fields_returns_422(client):
    run_id = _run(client)
    response = client.post(f'/api/runs/{run_id}/revocations',
                           json=dict(case='A', field='x', day=8, note='审批撤销'))
    assert response.status_code == 422
    assert response.json['code'] == 'REVIEW_FIELDS'


def test_evidence_includes_revocation_ledger(client):
    run_id = _run(client)
    client.patch(f'/api/runs/{run_id}', json=dict(revision=0, status='APPROVED', note='批次签发'))
    client.post(f'/api/runs/{run_id}/revocations', json=dict(case='A', field=2, day=8, note='审批撤销'))
    packet = client.get(f'/api/runs/{run_id}/evidence').json
    assert [item['field'] for item in packet['revocations']] == [2]
    assert packet['review']['status'] == 'SUSPENDED'


def test_revocation_kind_accepted_by_intake(client):
    from test_revocation import approval_batch
    # 含 revocation kind 的来源仍可正常采信与执行
    response = client.post('/api/stages/intake', data={'file': (io.BytesIO(approval_batch()), 'in.csv')})
    assert response.status_code == 200
