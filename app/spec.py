COLUMNS = ('field', 'parent', 'grade', 'day', 'until_day')
KINDS = ('column', 'dependency', 'approval', 'revocation', 'audit')
PROJECT = {'name': '字段分级传播台', 'actor': '数据治理专员', 'stages': [('intake', '样例采信'), ('prepare', '依赖排序'), ('calculate', '分级传播'), ('policy', '标签验收'), ('balance', '运行对账')], 'chart': '字段分级', 'mark': '字'}
