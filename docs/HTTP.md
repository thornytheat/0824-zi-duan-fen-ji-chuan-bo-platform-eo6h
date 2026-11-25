# 阶段接口

`POST /api/stages/<stage>` 接收 `multipart/form-data`。字段 `sample=dirty`、`sample=clean` 或 `file=<CSV>` 三选一。阶段为 `intake`、`prepare`、`calculate`、`policy`、`balance`。预览不入库。

`POST /api/runs` 接收同样的输入，执行全批并返回运行报告。`GET /api/runs` 返回最近 50 批。`GET /api/runs/<id>` 查询一批和当前复核状态。

`PATCH /api/runs/<id>` 接收 `revision`、`status` 和 `note`。状态使用 `APPROVED` 或 `HELD`。冲突返回 409，客户端读取新版本后重试。

`POST /api/runs/<id>/revocations` 受理针对原审批单的降级撤销，接收 `case`、`field`、`day`（生效日）和 `note`。撤销必须指向来源中真实存在的审批单，且生效日不得早于该分组的核验日，否则分别返回 404 与 409。撤销入账后沿字段依赖重算：核验日早于生效日的签发结果照旧保留为已签标签，重算值超过已签标签的分组标记 `SUPPLY_SUSPENDED` 并停止按低级供数，同批仍合格的分组继续可用。已撤销的审批单不能重复撤销。`GET /api/runs/<id>/revocations` 返回该批的撤销台账。

撤销与签发共用同一写锁：撤销入账后，再尝试签发偏低标签会返回 409 `UNRESOLVED_ISSUES`；已签发批次因撤销出现停用分组时，批次状态转为 `SUSPENDED`。

`GET /api/runs/<id>/evidence` 下载内含运行清单、行号隔离、业务证据、撤销台账和复核信息的 JSON。
