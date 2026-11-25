"""降级撤销台账：晚到撤销重算、分组级停用与并发签发护栏。"""
import pytest

from app.business import DomainIssue
from app.review.ledger import accept
from app.review.service import execute, review
from conftest import csv_data


def approval_batch():
    # A 组：字段1 级3 -> 字段2 自身1，审批单允许降到1，核验日7，签出标签1
    group_a = [
        ['A01', 'A', 'column', '1', '0', '3', '0', '0', '来源'],
        ['A02', 'A', 'column', '2', '0', '1', '0', '0', '来源'],
        ['A03', 'A', 'dependency', '2', '1', '0', '0', '0', '来源'],
        ['A04', 'A', 'approval', '2', '0', '1', '4', '12', '降级审批'],
        ['A05', 'A', 'audit', '2', '0', '1', '7', '0', '核验'],
    ]
    # B 组：自然级2，无降级，同批仍合格
    group_b = [
        ['B01', 'B', 'column', '1', '0', '2', '0', '0', '来源'],
        ['B02', 'B', 'column', '2', '0', '2', '0', '0', '来源'],
        ['B03', 'B', 'dependency', '2', '1', '0', '0', '0', '来源'],
        ['B04', 'B', 'audit', '2', '0', '2', '7', '0', '核验'],
    ]
    return csv_data(group_a + group_b)


def cases_of(run):
    return {case['case']: case for case in run['report']['cases']}


def test_late_revocation_suspends_only_low_label_group(store):
    run = execute(store, approval_batch())
    run = review(store, run['id'], dict(revision=0, status='APPROVED', note='整批签发'))
    updated = accept(store, run['id'], dict(case='A', field=2, day=8, note='降级审批撤销'))
    cases = cases_of(updated)
    assert updated['status'] == 'SUSPENDED'
    assert cases['A']['status'] == 'SUPPLY_SUSPENDED'
    assert cases['A']['measure']['value'] == 3
    assert cases['A']['signed_label'] == 1
    assert cases['A']['measure']['evidence']['revoked'] == ['2']
    assert cases['A']['measure']['evidence']['approved'] == []
    # 同批仍合格的分组继续可用，不整批停用
    assert cases['B']['status'] == 'READY'
    assert cases['B']['measure']['value'] == 2
    assert updated['report']['balance']['suspended'] == 1
    assert updated['report']['balance']['releasable'] is False


def test_revocation_keeps_group_when_recomputed_label_not_exceeded(store):
    # A 组审批只把字段2 从2 降到2 以下无效，这里构造重算值不超过已签标签的场景：
    # 已签标签2，撤销一个让字段3 从3 降到2 的审批，重算仍为2（不超过标签），分组保持可用。
    rows = [
        ['C01', 'C', 'column', '1', '0', '2', '0', '0', '来源'],
        ['C02', 'C', 'column', '2', '0', '2', '0', '0', '来源'],
        ['C03', 'C', 'dependency', '2', '1', '0', '0', '0', '来源'],
        ['C04', 'C', 'approval', '2', '0', '2', '4', '12', '平级审批'],
        ['C05', 'C', 'audit', '2', '0', '2', '7', '0', '核验'],
    ]
    run = execute(store, csv_data(rows))
    run = review(store, run['id'], dict(revision=0, status='APPROVED', note='批次签发'))
    updated = accept(store, run['id'], dict(case='C', field=2, day=8, note='撤销平级审批'))
    case = cases_of(updated)['C']
    assert updated['status'] == 'APPROVED'
    assert case['status'] == 'READY'
    assert case['measure']['value'] == 2


def test_revocation_effective_before_verification_is_rejected(store):
    run = execute(store, approval_batch())
    run = review(store, run['id'], dict(revision=0, status='APPROVED', note='批次签发'))
    with pytest.raises(DomainIssue, match='REVOKED_BEFORE_VERIFICATION'):
        accept(store, run['id'], dict(case='A', field=2, day=5, note='过早撤销'))
    # 历史结果照旧
    fresh = store.load(run['id'])
    assert fresh['status'] == 'APPROVED'
    assert cases_of(fresh)['A']['measure']['value'] == 1
    assert store.revocations(run['id']) == []


def test_revocation_effective_on_verification_day_is_accepted(store):
    # 核验日为7，生效日等于核验日（不早于）应当受理
    run = execute(store, approval_batch())
    review(store, run['id'], dict(revision=0, status='APPROVED', note='批次签发'))
    updated = accept(store, run['id'], dict(case='A', field=2, day=7, note='当日生效撤销'))
    case = cases_of(updated)['A']
    assert updated['status'] == 'SUSPENDED'
    assert case['status'] == 'SUPPLY_SUSPENDED'
    assert case['measure']['value'] == 3


def test_revocation_must_target_existing_approval(store):
    run = execute(store, approval_batch())
    with pytest.raises(DomainIssue, match='REVOCATION_TARGET_MISSING'):
        accept(store, run['id'], dict(case='A', field=9, day=8, note='无目标审批'))
    with pytest.raises(DomainIssue, match='REVOCATION_TARGET_MISSING'):
        accept(store, run['id'], dict(case='Z', field=2, day=8, note='无目标分组'))


def test_approval_can_only_be_revoked_once(store):
    run = execute(store, approval_batch())
    review(store, run['id'], dict(revision=0, status='APPROVED', note='批次签发'))
    accept(store, run['id'], dict(case='A', field=2, day=8, note='首次撤销'))
    with pytest.raises(DomainIssue, match='APPROVAL_ALREADY_REVOKED'):
        accept(store, run['id'], dict(case='A', field=2, day=9, note='重复撤销'))
    assert len(store.revocations(run['id'])) == 1


def test_revocation_fields_validated(store):
    run = execute(store, approval_batch())
    for bad in [dict(case='A', field='x', day=8, note='撤销'),
                dict(case='A', field=2, day=-1, note='撤销'),
                dict(case='A', field=2, day=8, note='短'),
                dict(case='', field=2, day=8, note='撤销')]:
        with pytest.raises(DomainIssue, match='REVIEW_FIELDS'):
            accept(store, run['id'], bad)


def test_suspended_run_cannot_be_reapproved(store):
    run = execute(store, approval_batch())
    run = review(store, run['id'], dict(revision=0, status='APPROVED', note='批次签发'))
    suspended = accept(store, run['id'], dict(case='A', field=2, day=8, note='审批撤销'))
    with pytest.raises(DomainIssue, match='UNRESOLVED_ISSUES'):
        review(store, suspended['id'],
               dict(revision=suspended['revision'], status='APPROVED', note='试图再签'))


def test_revocation_before_signing_blocks_low_label(store):
    run = execute(store, approval_batch())
    accept(store, run['id'], dict(case='A', field=2, day=8, note='先撤销'))
    # 撤销入账后不能再签出偏低标签
    with pytest.raises(DomainIssue, match='UNRESOLVED_ISSUES'):
        review(store, run['id'], dict(revision=0, status='APPROVED', note='试图签发'))
    assert store.load(run['id'])['status'] == 'PENDING'


def test_revocation_rerun_is_deterministic(store):
    run = execute(store, approval_batch())
    review(store, run['id'], dict(revision=0, status='APPROVED', note='批次签发'))
    first = accept(store, run['id'], dict(case='A', field=2, day=8, note='审批撤销'))
    second = store.load(run['id'])
    assert first['report'] == second['report']


def test_revocation_preserves_run_manifest(store):
    run = execute(store, approval_batch())
    original_manifest = run['report']['manifest']
    review(store, run['id'], dict(revision=0, status='APPROVED', note='批次签发'))
    updated = accept(store, run['id'], dict(case='A', field=2, day=8, note='审批撤销'))
    assert updated['report']['manifest'] == original_manifest
    assert updated['report']['manifest']['sha256'] == original_manifest['sha256']
