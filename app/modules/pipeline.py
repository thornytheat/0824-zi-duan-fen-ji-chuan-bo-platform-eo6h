from app.business import DomainIssue, by_kind
from app.intake.service import inspect
from app.modules.calculate import compute
from app.modules.grouping import case_groups
from app.modules.policy import policy
from app.modules.prepare import prepare
from app.modules.reconcile import balance


def evaluate(rows, stage, source_revocations=(), ledger=(), signed_labels=None):
    case = {'case':rows[0]['case'],'records':[r['record'] for r in rows], 'status':'READY'}
    audit_day = next(r['day'] for r in rows if r['kind']=='audit')
    # 来源中的撤销按核验日快照判断；台账撤销在受理时已校验生效日不早于核验日，一律生效。
    active = [entry for entry in source_revocations if entry['day'] <= audit_day]
    active.extend(dict(field=entry['field'], day=entry['day']) for entry in ledger)
    try:
        case['prep'], payload = prepare(rows, revoked=active)
        if stage >= 3:
            case['measure'] = compute((*payload, {entry['field'] for entry in active}))
        if stage >= 4:
            case.update(policy(case['measure']))
            label = (signed_labels or {}).get(case['case'])
            if label is not None and case['measure']['value'] > label:
                case['status'] = 'SUPPLY_SUSPENDED'
                case['signed_label'] = label
    except DomainIssue as error:
        case['status'] = error.code
    return case


def run(data, stage=5, ledger=()):
    intake = inspect(data)
    output = {'intake': {k:v for k,v in intake.items() if k!='rows'}}
    if stage == 1:
        return output
    source_revocations = [dict(field=r['field'], day=r['day']) for r in by_kind(intake['rows'],'revocation')]
    signed_labels = {entry['case']: entry['label'] for entry in ledger if entry.get('label') is not None}
    cases = [evaluate(rows, stage, source_revocations, ledger, signed_labels)
             for _, rows in case_groups(intake['rows'])]
    output['cases'] = cases
    if stage >= 5:
        output['balance'] = balance(intake,cases)
    return output
