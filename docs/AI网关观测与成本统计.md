# AI 网关观测与成本统计

平台现在会从统一 AI 网关记录调用状态、耗时、输入/输出 Token 和可选成本。观测失败不会影响 AI 请求本身。

## 建表

新增表只有 `ai_call_records` 和 `ai_model_pricing`，不会删除或修改现有业务表。

由于当前仓库历史上没有完整的 `users` migration，已有部署建议在确认备份后执行下面的增量命令：

```powershell
& .\\.venv\\python.exe manage.py ensure_ai_observability
```

命令只检查表名并创建缺失表，不执行删除、修改或数据迁移。迁移历史完整的新环境也可以执行：

```powershell
& .\\.venv\\python.exe manage.py migrate ai_gateway
```

## 查看

- Django Admin：`/admin/` 下的 **AI call records** 和 **AI model pricing**。
- 管理员只读 API：`/api/ai/call-records/`。
- 聚合统计：`/api/ai/call-records/stats/`。

API 默认只允许管理员访问。调用记录不会保存 API Key、请求正文或响应正文。

## 配置价格

在 Admin 的 **AI model pricing** 中按“每百万 Token”填写输入和输出价格。`model_keyword` 可填写模型名子串；留空表示该供应商的兜底价格。未配置价格时仍记录 Token，但单条记录成本为空、统计接口显示 `0.000000`，不会猜测厂商价格。

如需暂时停用观测写库，在 `.env` 设置：

```text
AI_OBSERVABILITY_ENABLED=False
```
