from app.business import DomainIssue, by_kind, prepared, single


def prepare(rows):
    from graphlib import TopologicalSorter, CycleError
    audit = single(rows,'audit')
    columns = by_kind(rows,'column')
    grades = {r['field']:r['grade'] for r in columns}
    if len(grades) != len(columns) or any(level > 3 for level in grades.values()) or audit['grade'] > 3:
        raise DomainIssue('UNKNOWN_GRADE')
    if audit['field'] not in grades:
        raise DomainIssue('UNKNOWN_FIELD')
    parents = {field:set() for field in grades}
    for row in by_kind(rows,'dependency'):
        field, parent = row['field'], row['parent']
        if field not in grades or parent not in grades:
            raise DomainIssue('UNKNOWN_FIELD')
        parents[field].add(parent)
    try:
        order = list(TopologicalSorter({f:sorted(parents[f]) for f in sorted(parents)}).static_order())
    except CycleError as error:
        raise DomainIssue('LINEAGE_CYCLE') from error
    permits, expired = {}, set()
    for row in by_kind(rows,'approval'):
        field, start, end = row['field'], row['day'], row['until_day']
        if field not in grades or not start < end or not grades[field] <= row['grade'] <= 3:
            raise DomainIssue('INVALID_APPROVAL')
        if start <= audit['day'] < end:
            if field in permits:
                raise DomainIssue('APPROVAL_OVERLAP')
            permits[field] = row['grade']
        elif end <= audit['day']:
            expired.add(field)
    return prepared(len(order),{'columns':len(order),'active_approvals':len(permits),'snapshot_day':audit['day']},(grades,parents,order,permits,expired,audit))
