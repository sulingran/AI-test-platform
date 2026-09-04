# Docker 部署与数据隔离

## 适用范围

该部署文件适用于在一台新的 Docker 主机上运行 TestHub。Compose 内置 MySQL 使用独立的命名卷 `testhub_mysql_data`，不会挂载宿主机 MySQL 数据目录，也不会连接另一台电脑的数据库。

## 启动

```powershell
Copy-Item .docker_env.example .docker_env
# 编辑 .docker_env，至少替换 SECRET_KEY、MYSQL_ROOT_PASSWORD、DB_PASSWORD
docker compose --env-file .docker_env up -d --build
```

默认地址：

- 前端：`http://localhost:18081`
- 后端：`http://localhost:18181/api/docs/`
- 健康检查：`http://localhost:18081/health`

## 数据库安全边界

- 当前仓库历史迁移图并不完整，不能把全新空 MySQL 直接当作已初始化业务库；首次部署前需准备兼容的业务数据库或导入经过审核的备份。
- Compose 的 MySQL 卷与宿主机及其他电脑完全隔离，但“隔离”不等于自动生成业务表；本项目不会为了启动而猜测或生成历史业务迁移。
- 容器启动不会执行 `makemigrations`。
- 容器启动不会执行 `migrate`。
- `SCHEMA_SETUP_ENABLED=False` 时不会执行任何结构补充命令。
- 只有在已确认目标数据库并完成备份后，才可将 `SCHEMA_SETUP_ENABLED=True`，该模式只调用 `ensure_openapi_import` 和 `ensure_ai_observability`，只创建缺失表或字段，不删除表、不删除数据。
- 查看待补结构而不改库：

```powershell
docker compose --env-file .docker_env run --rm backend python manage.py ensure_openapi_import --check
docker compose --env-file .docker_env run --rm backend python manage.py ensure_ai_observability --check
```

## 常用检查

```powershell
docker compose --env-file .docker_env ps
docker compose --env-file .docker_env logs --tail=100 backend scheduler frontend
docker compose --env-file .docker_env config --quiet
```

`scheduler` 是独立容器，使用 `run_all_scheduled_tasks --once` 周期执行，间隔由 `SCHEDULER_INTERVAL` 控制。Nginx 已配置 SPA 路由、API/SSE、WebSocket、静态文件、媒体文件和 100 MB 上传限制。

## 停止

```powershell
docker compose --env-file .docker_env stop
```

不要使用 `docker compose down -v`，否则会删除本 Compose 项目的命名卷及其中数据。
