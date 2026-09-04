# OpenAPI/Swagger 导入与数据库升级

## 功能范围

- 支持 OpenAPI 3.0、OpenAPI 3.1 和 Swagger 2.0。
- 支持 JSON、YAML 文件或直接粘贴文档内容。
- 解析接口方法、路径、Tag、Query/Header/Path 参数、请求体、认证占位符、响应 Schema 和示例。
- 导入前可预览并勾选接口，可按 Tag 创建子集合。
- 重复接口默认跳过，也可显式选择“更新契约”。更新时保留已有断言和前后置脚本。
- 只解析文档内部 `$ref`，拒绝外部文件和远程引用。
- 上传文件和解析结果不会通过 API 暴露文件下载地址；疑似密码、Token、Secret 的示例值会替换成占位符。

## 数据库变更

本功能只执行以下增量变更：

- 在 `api_requests` 增加 `request_schema`、`response_schemas`、`path_params`、`response_examples`、`deprecated`、`openapi_path`。
- 新建 `api_documents` 表。

不会删除表、删除字段、清空数据或覆盖已有接口。项目原有 `api_testing` 迁移基线不完整，因此旧库使用幂等兼容命令升级：

```powershell
& .\.venv\python.exe manage.py ensure_openapi_import --check
& .\.venv\python.exe manage.py ensure_openapi_import
```

第一条命令只检查缺失项；第二条命令仅创建缺失字段和表。重复执行时不会重复修改。

AI 调用观测表是独立变更，继续使用：

```powershell
& .\.venv\python.exe manage.py ensure_ai_observability --check
& .\.venv\python.exe manage.py ensure_ai_observability
```

## 使用注意

- 正式环境执行数据库命令前仍应保留备份，并确保应用使用的 MySQL 账号具有 `ALTER TABLE` 和 `CREATE TABLE` 权限。
- 文档导入成功只代表契约已进入平台，不代表目标接口网络可达或断言已经完备。
- OpenAPI 文档中不要填写真实密码或 Token；平台会进行字段名级脱敏，但不能代替源文档的密钥管理。
- 如选择“更新契约”，系统按 `HTTP 方法 + OpenAPI 原始路径` 匹配接口，覆盖 URL、参数、请求体和 Schema 等契约字段。
