# Phase 2.9：MySQL、上传文件和 Chroma 组合恢复

`backend/scripts/rehearse_mysql_restore.py` 将 Phase 2.7 的 MySQL dump 与 Phase 2.8 的文件快照组合到一次停写合成演练中。没有新增依赖，不接受现有业务库或业务目录作为参数。

在 backend 目录，使用现有 Python 3.11 环境和 PATH 中的 MySQL 8.4 mysql/mysqldump：

```powershell
python scripts/rehearse_mysql_restore.py --host 127.0.0.1 --port 3307 --user root
```

密码来自进程环境 `RAG4_TEST_MYSQL_PASSWORD`；子进程连接 URL 也仅通过环境传递，不写入命令参数、备份清单或报告。需要新建测试库权限。退出码 0 通过，1 失败；报告记录阶段和异常类型，不回显含 SQL 或连接信息的错误正文。数据库、备份包和恢复目录均保留，不自动清理。

## 执行链路

1. 创建随机前缀的 source/after 两个新库及临时目录。seed 子进程在空源库创建 baseline 表并执行仓库 002–006 迁移，通过结构门禁，再创建中文文档、准备任务、ChunkSet、真实 Chroma baseline 和候选、版本及 active 指针。模型为确定性三维 Fake Adapter。
2. 等 seed 退出，确保合成系统所有写入者和 Chroma 句柄关闭。记录所有表的行数与内容摘要，导出 SQL 到源目录，再把 SQL、上传文件、Chroma 和验证清单捕获为一个快照。
3. 将可信 manifest SHA-256 写入包外报告；报告还记录 dump 和迁移脚本摘要、MySQL 版本、UTC 时间、阶段及总耗时。检查源库摘要在导出捕获前后不变。
4. `restore_pair` 先拒绝非演练库/非空库，校验整个文件包和 SQL 存在性，再恢复到新目录。SQL 导入使用清单绑定的摘要，导入后复核十五张表数据和结构门禁。
5. verify 子进程只在恢复库重映射合成文档路径，验证原文、active 指针、清单、ChunkSet、向量来源及摘要并执行查询；停用恢复库 active，验证 baseline 查询。
6. 最后复核源库所有行摘要、源文件清单完全不变。成功报告包含导入后、路径映射和查询之前的逐表摘要。

SQL 导入失败可能留下部分恢复数据；文件失败也可能保留不完整目录。不会报告成功或替换业务配置，重试必须创建新库和新目录。备份包被篡改时在导入 SQL 前拒绝；没有自动修复或对旧库执行删除型回滚。

## 本次证据与边界

2026-09-22 在 MySQL 8.4.9/3307 通过，32882ms。库为 `rag4_restore_665566bc97f6_source` 和 `rag4_restore_665566bc97f6_after`；报告、源目录、备份包和恢复目录位于 `C:\Users\gy\AppData\Local\Temp\rag4_mysql_restore_onsvwirc`。完整验证记录见 [基线](../../RAG4_BASELINE.md)。

这是停写**合成系统**的组合恢复证据，不是生产上线许可。没有覆盖真实大库、所有多用户状态、并发在线备份、跨主机恢复、服务停写编排或模型语义质量；模型未调用外部 API。三个演练入口都不修改应用的业务 `.env`。正式操作仍需确认专用库、备份保管与停写窗口、部署配置及业务验收。后续开发应补 Phase 2 的受权限保护的任务管理入口和验收，Graph/Agent/研究前端未因此完成。
