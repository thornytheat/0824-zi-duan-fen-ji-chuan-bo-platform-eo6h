EXPECTED = {'0001': (3, 1, 'READY'),
 '0002': (2, 3, 'READY'),
 '0003': (0, None, 'LINEAGE_CYCLE'),
 '0004': (2, 3, 'LABEL_TOO_LOW')}
EVIDENCE = {'0001': {'grades': {'1': 3, '2': 1, '3': 1}, 'approved': [2], 'expired': [], 'revoked': []},
 '0004': {'grades': {'1': 3, '2': 3}, 'approved': [], 'expired': [2], 'revoked': []}}
