from app.business import decision


def policy(result):
    return decision(result,'LABEL_TOO_LOW' if result['value'] > result['expected'] else None,upper_bound=True)
