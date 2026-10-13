# Phase 2.6：只读结构门禁

`app.services.schema_preflight.inspect_schema(engine) -> SchemaReport` 接收显式 SQLAlchemy Engine，仅执行结构元数据读取。不会创建数据库、修改表、初始化应用、调用模型或切换 active 指针。无需新增依赖。

当前范围为 002–007 的九张 Phase 2 表（Phase 2.15 纳入创建幂等映射），以及外键依赖的 users.id / documents.id；并非完整应用上线检查。检查字段存在性、类型和长度、nullable、主键、必需唯一键、索引前缀、外键目标和 ON DELETE。MySQL 另检查 InnoDB、表级 utf8mb4_unicode_ci 与显式字段 collation（包括幂等键 utf8mb4_bin）。额外表/字段允许存在。默认值、触发器、权限、业务数据、备份恢复及在线 DDL 风险未覆盖。

返回值包含 dialect、ready、migration_files、issues（table/code/subject）和 duration_ms，不包含连接 URL、密码或业务行内容。缺表会给出按依赖排序的脚本列表；已有表漂移只报告问题，不生成自动修复 SQL。部分迁移也会列出相应脚本，但执行 CREATE TABLE IF NOT EXISTS **不能修复已有表**，必须处理其余 issues 后重新检查。

在 backend 目录执行（密码由当前进程环境注入，不放到命令行参数或配置库）：

```powershell
python scripts/check_index_schema.py --host 127.0.0.1 --port 3307 --user root --database YOUR_RAG4_DATABASE
```

环境变量为 `RAG4_TEST_MYSQL_PASSWORD`。必须显式选择 database；默认端口 3307。建议使用仅有结构读取权限的账号。JSON 输出；退出码 0 = 本门禁通过，1 = 缺表或结构差异，2 = 缺少密码环境变量或检查失败。失败只输出错误分类，不打印驱动连接详情。

上线流程：选定 RAG4 专用库 → 备份和副本恢复演练 → 只读检查 → 在副本审查并执行必要的增量脚本 → 再检查及重建/激活/回滚验证 → 安排正式迁移。本工具只实现“检查”环节；绝不可用包含 DROP DATABASE 的历史 init_db.sql 升级已有库。

2026-09-17 实测：MySQL 8.4.9 / 3307 既有合成验证库通过（68ms）；旧 rag_high 被正确识别为缺少全部八张 Phase 2 表（51ms），列出 002–006，未写入任何业务表。首次实测发现反射的 VARCHAR 多出 CHARACTER SET 导致误报，已规范化类型显示并保留独立 collation 检查，补充回归测试。
