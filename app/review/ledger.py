"""降级撤销台账：受理针对原审批单的撤销，沿字段依赖重算并停用偏低标签。"""
import json

from app.business import DomainIssue
from app.intake.service import inspect
from app.modules.pipeline import run as evaluate_run
from app.review.service import now


def _entry(values):
    if not isinstance(values, dict):
        raise DomainIssue('REVIEW_FIELDS')
    case, field, day, note = values.get('case'), values.get('field'), values.get('day'), values.get('note')
    if not isinstance(case, str) or not case.strip():
        raise DomainIssue('REVIEW_FIELDS')
    if type(field) is not int or field < 0:
        raise DomainIssue('REVIEW_FIELDS')
    if type(day) is not int or day < 0 or not isinstance(note, str) or not (3 <= len(note.strip()) <= 200):
        raise DomainIssue('REVIEW_FIELDS')
    return {'case': case.strip(), 'field': field, 'day': day, 'note': note.strip()}


def _first_labels(ledger):
    labels = {}
    for entry in ledger:
        if entry.get('label') is None or entry['case'] in labels:
            continue
        labels[entry['case']] = entry['label']
    return labels


def _store_revocations(db, run_id):
    rows = db.execute('SELECT case_id, field, day, label FROM revocations WHERE run_id=? ORDER BY id',
                      (run_id,)).fetchall()
    return [dict(case=row['case_id'], field=int(row['field']), day=row['day'], label=row['label']) for row in rows]


def _refresh(db, store, run_id, source, merged, current, entry_note):
    """撤销入账后沿字段依赖重算，超过已签标签的分组停止按低级供数。"""
    fresh = evaluate_run(source, ledger=merged)
    # 重算只更新业务结果，原运行清单（来源指纹、规则版本等）保持不变。
    fresh['manifest'] = json.loads(current['report'])['manifest']
    suspended_cases = [case['case'] for case in fresh['cases'] if case['status'] == 'SUPPLY_SUSPENDED']
    if current['status'] == 'APPROVED':
        if suspended_cases:
            return store.update_report(db, run_id, fresh, 'SUSPENDED', entry_note, now()), fresh, suspended_cases
        return store.update_report(db, run_id, fresh, 'APPROVED', current['note'], current['reviewed']), fresh, []
    return store.update_report(db, run_id, fresh), fresh, suspended_cases


def accept(store, run_id, values):
    entry = _entry(values)
    with store.transaction() as db:
        row = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise DomainIssue('RUN_NOT_FOUND')
        current = dict(row)
        report = json.loads(current['report'])
        source_row = db.execute('SELECT data FROM sources WHERE run_id=?', (run_id,)).fetchone()
        if source_row is None:
            raise DomainIssue('SOURCE_NOT_KEPT')
        source = source_row['data']

        intake = inspect(source)
        groups = {}
        for source_row_data in intake['rows']:
            groups.setdefault(source_row_data['case'], []).append(source_row_data)
        if entry['case'] not in groups:
            raise DomainIssue('REVOCATION_TARGET_MISSING')
        rows = groups[entry['case']]
        audit_day = next((r['day'] for r in rows if r['kind'] == 'audit'), None)
        target = next((r for r in rows if r['kind'] == 'approval' and r['field'] == entry['field']), None)
        if target is None:
            raise DomainIssue('REVOCATION_TARGET_MISSING')
        # 核验日早于撤销生效日的签发结果照旧：生效日不得早于核验日。
        if entry['day'] < audit_day:
            raise DomainIssue('REVOKED_BEFORE_VERIFICATION')

        ledger = _store_revocations(db, run_id)
        # 一张审批单只允许一条生效撤销，重复受理直接拒绝。
        if any(saved['field'] == entry['field'] for saved in ledger):
            raise DomainIssue('APPROVAL_ALREADY_REVOKED')

        labels = _first_labels(ledger)
        if current['status'] == 'APPROVED' and entry['case'] not in labels:
            signed = next((case for case in report['cases'] if case['case'] == entry['case']), None)
            if signed is not None and 'measure' in signed:
                labels[entry['case']] = signed['measure']['value']
        stored = dict(entry)
        stored['label'] = labels.get(entry['case'])
        store.add_revocation(db, run_id, stored, now())

        merged = ledger + [stored]
        revision, _, _ = _refresh(db, store, run_id, source, merged, current, entry['note'])
    result = store.load(run_id)
    result['applied_revision'] = revision + 1
    result['revocations'] = store.revocations(run_id)
    return result


def refresh_approved(store, db, run_id, source, report):
    """签发前对已入账撤销做最后一次重算，撤销入账后不能再签出偏低标签。"""
    ledger = _store_revocations(db, run_id)
    if not ledger:
        return report
    fresh = evaluate_run(source, ledger=ledger)
    fresh['manifest'] = report['manifest']
    return fresh


def review(store, run_id, revision, status, note):
    """与撤销共用同一写锁的复核入口，保证撤销入账后无法签出偏低标签。"""
    with store.transaction() as db:
        row = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise DomainIssue('RUN_NOT_FOUND')
        current = dict(row)
        if revision != current['revision']:
            raise DomainIssue('STALE_REVIEW')
        if current['status'] == 'APPROVED':
            raise DomainIssue('RUN_FINALIZED')
        report = json.loads(current['report'])
        source_row = db.execute('SELECT data FROM sources WHERE run_id=?', (run_id,)).fetchone()
        source = source_row['data'] if source_row is not None else b''
        if status == 'APPROVED':
            report = refresh_approved(store, db, run_id, source, report)
            if not report['balance']['releasable'] or any(case['status'] == 'SUPPLY_SUSPENDED' for case in report['cases']):
                raise DomainIssue('UNRESOLVED_ISSUES')
        store.update_report(db, run_id, report, status, note, now())
    return store.load(run_id)
