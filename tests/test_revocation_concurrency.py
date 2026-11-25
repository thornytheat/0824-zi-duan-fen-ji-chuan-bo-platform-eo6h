"""撤销与签发并发：撤销入账后不能再签出偏低标签。"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app.business import DomainIssue
from app.review.ledger import accept
from app.review.service import execute, review
from test_revocation import approval_batch, cases_of


def test_revocation_and_approval_never_leave_low_label_signed(store):
    run = execute(store, approval_batch())
    barrier = Barrier(2)

    def revoke():
        barrier.wait(3)
        try:
            return accept(store, run['id'], dict(case='A', field=2, day=8, note='并发撤销'))['status']
        except DomainIssue as error:
            return error.code

    def approve():
        barrier.wait(3)
        try:
            return review(store, run['id'], dict(revision=0, status='APPROVED', note='并发批次签发'))['status']
        except DomainIssue as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda fn: fn(), [revoke, approve]))

    final = store.load(run['id'])
    assert final['status'] != 'APPROVED'
    assert len(store.revocations(run['id'])) == 1
    case_a = cases_of(final)['A']
    assert case_a['measure']['value'] == 3
    if 'APPROVED' in outcomes:
        # 签发先赢：撤销随后必须把批次转为停用
        assert final['status'] == 'SUSPENDED'
        assert case_a['status'] == 'SUPPLY_SUSPENDED'
        assert case_a['signed_label'] == 1
    else:
        # 撤销先赢：签发被挡，无已签标签，批次保持待复核
        assert 'UNRESOLVED_ISSUES' in outcomes
        assert final['status'] == 'PENDING'
        assert not final['report']['balance']['releasable']


def test_parallel_revocations_serialize(store):
    run = execute(store, approval_batch())
    review(store, run['id'], dict(revision=0, status='APPROVED', note='批次签发'))
    barrier = Barrier(2)

    def attempt(field):
        barrier.wait(3)
        try:
            return accept(store, run['id'], dict(case='A', field=field, day=8, note='并发审批撤销'))
        except DomainIssue as error:
            return error.code

    # 同一审批单的两个并发撤销，至多一个入账
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [2, 2]))
    codes = [item if isinstance(item, str) else 'OK' for item in results]
    assert codes.count('OK') == 1
    assert len(store.revocations(run['id'])) == 1
