# Phase 2.7：合成数据库备份恢复演练

新增 `backend/scripts/rehearse_index_migration.py`，用于验证关系数据库增量迁移与逻辑备份恢复。仅创建随机命名的三个测试库，不接受现有数据库作为参数，不执行 DROP，不覆盖业务库。数据库、SQL 备份、合成 Markdown 和 report.json 都保留。

## 执行

在 backend 目录使用现有 Python 环境，安装好的 MySQL 8.4 `mysql`、`mysqldump` 必须位于 PATH。没有新增 Python 依赖；MySQL 客户端来自本机 MySQL Server 8.4 安装目录。

```powershell
python scripts/rehearse_index_migration.py --host 127.0.0.1 --port 3307 --user root
```

密码由 `RAG4_TEST_MYSQL_PASSWORD` 进程环境变量提供，子进程使用 MYSQL_PWD，密码不出现在命令行参数、报告或 Git 文件中。此脚本需要创建测试库权限，不能使用只读门禁账号。退出码 0 为通过，1 为执行失败，2 为缺少密码或客户端工具。失败报告只记录阶段和异常类型，不回显可能含敏感内容的驱动/客户端错误。

## 已验证链路

1. 新建 source、before、after 三个独立库；source 创建七张 baseline ORM 表，写入一个合成用户和文档。
2. 使用 mysqldump 单事务备份 baseline；只在客户端成功且文件非空时将 partial 发布为 SQL 备份，保留 SHA-256。
3. source 执行仓库 002–006 增量脚本，通过 schema_preflight，并校验原七张表数据摘要不变。
4. 调用真实切分准备服务，生成成功任务及有效 ChunkSet，再备份十五张表。
5. 恢复前检查目标库名称和空库条件、备份摘要；分别恢复 baseline 和迁移后备份，逐表比较行数和内容摘要。
6. 新版本恢复库通过结构门禁；baseline 恢复库再次迁移并确认旧数据不变；新版本恢复库重放迁移并确认所有数据不变。

报告包含 UTC 起始时间、总耗时、MySQL 版本、测试库名称、执行阶段、备份与迁移文件 SHA-256、逐表行数和内容摘要。脚本只处理当前无存储过程、触发器或事件的合成数据；SQL 按当前简单迁移格式执行，不是通用 SQL 解析器。

## 边界和下一步

这证明的是**合成关系数据库**的逻辑备份恢复和增量脚本可重放性。仅 users、documents、document_chunk_sets、document_index_jobs 含样例行，其余表为空；不证明真实大库性能、所有业务状态覆盖、在线一致性或完整灾难恢复。

Chroma、上传文件、模型制品、密钥及部署配置没有纳入备份；恢复的文档路径仍指向保留的合成文件。没有对业务库执行迁移，没有完成正式 RAG4 专用库上线。下一切片应验证上传文件与向量目录的配套恢复、索引清单与实际向量一致性，再确定正式迁移窗口。回退应用时保留新增表，不执行删除型反向迁移。

两次真实演练的本地位置和测试结果见 [基线记录](../../RAG4_BASELINE.md)。

后续 Phase 2.8 已补充 [停写文件与 Chroma 配套恢复](offline_restore.md)，使用合成 SQLite 验证关联数据、向量和上传文件；尚未与本页 MySQL 演练合并为统一恢复流程。
