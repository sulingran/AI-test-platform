# Prompt 版本管理

Prompt 种子采用文件版本管理，不依赖数据库迁移，也不会自动写入现有数据库。

当前 `writer` 和 `reviewer` 的 v1 分别沿用 `docs/tester.md` 与 `docs/tester_pro.md`。后续版本放在 `docs/prompts/<类型>/vN.md`，例如 `docs/prompts/writer/v2.md`。

版本文件名必须是 `v` 加数字的 Markdown 文件。读取时默认选择数字最大的版本；如果没有显式版本文件，则使用旧文档作为 v1。

可在 D 盘项目目录执行只读校验：

```powershell
& .\\.venv\\python.exe manage.py validate_prompts
```

该命令只读取文件并输出 SHA-256，不执行 `migrate`、`makemigrations` 或任何种子写库操作。
