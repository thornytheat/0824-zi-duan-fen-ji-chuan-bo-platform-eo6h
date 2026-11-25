from app.business import measured


def compute(data):
    grades, parents, order, permits, expired, audit, revoked = data
    inherited = {}
    approved = []
    for field in order:
        level = max([grades[field],*(inherited[p] for p in parents[field])])
        if permits.get(field,level) < level:
            level = permits[field]
            approved.append(field)
        inherited[field] = level
    evidence = {'grades':{str(k):v for k,v in inherited.items()},
                'approved':sorted(approved),
                'expired':sorted(expired-set(permits)),
                'revoked':sorted(str(field) for field in revoked)}
    return measured(inherited[audit['field']],audit['grade'],'级',evidence)
