# Phase 2.8：停写状态下的文件与 Chroma 配套恢复

后续 Phase 2.9 已完成 [MySQL 组合演练](mysql_combined_restore.md)；本文保留 SQLite 切片的独立契约和验证边界。

## 接口与前置条件

新增 `app.services.offline_snapshot`：

- `capture(source: Path, destination: Path) -> str`：复制完整目录树，验证复制前后源与副本的文件清单一致，最后写入 manifest.json，返回其 SHA-256。
- `verify(bundle: Path, expected_manifest_sha256: str) -> dict`：使用包外保存的可信摘要校验清单，再检查全部文件、目录、大小与内容摘要；多余文件也拒绝。
- `restore(bundle, destination, *, expected_manifest_sha256) -> None`：先校验包，再恢复到全新目录，最后完整复核。异常时不返回成功，可能保留不完整目标，必须另选新路径重试。

**调用前必须停止全部写入者，并在捕获期间保持停写。** 工具本身不能停止应用、建立跨存储事务或证明服务已停写。前后摘要比较只能发现部分并发修改，不能替代停写。目标必须不存在且与源不重叠；拒绝符号链接和 Windows reparse point/junction，不通过清单中的路径拼接写文件。不删除历史数据，不替换应用目录，不自动修改 active 指针。

清单格式为 `rag4-offline-v1`，记录相对路径、空目录、文件长度与 SHA-256。调用方必须将返回摘要存放在包外可信记录中；它提供完整性检查，不是签名、加密、恶意本机写入防护或原子在线备份。失败目录保留供检查，不可作为成功恢复目录使用。无新增依赖。

## 可重复演练

在 backend 使用现有 Python/Chroma 环境运行：

```powershell
python scripts/rehearse_offline_restore.py
```

公开演练入口不接受现有业务目录，每次创建独立临时目录并保留报告。内部子进程 seed/verify 参数仅用于演练编排，不是生产恢复命令。

1. seed 子进程新建 SQLite、中文 Markdown 上传文件、真实 Chroma baseline，调用切分准备、候选构建、版本创建及激活服务。Embedding 使用确定性的三维 Fake Adapter，不调用远程模型。
2. 等 seed 进程退出后捕获目录树，此时数据库和 Chroma 均无写入者或未关闭句柄。库文件、上传目录、Chroma SQLite/HNSW 文件及验证清单一起打包。
3. 恢复到全新目录；verify 子进程仅在恢复的数据库中将合成文档路径映射到恢复后的上传文件，并验证原文摘要。
4. 验证原 active version/revision、ChunkSet/候选/清单来源关系和完整向量摘要，执行真实 Chroma 检索；然后在恢复库显式停用 active，校验 baseline 摘要并查询。原数据库摘要保持不变。

report.json 包含目录、范围、UTC 起始时间、耗时、外部清单摘要及成功/失败阶段。文件校验发生在恢复库首次打开之前；打开数据库或 Chroma 后文件可能变化，不应要求工作目录始终匹配备份的字节摘要。原始 bundle 保持不变。

## 验收边界

这是**停写合成 SQLite + 上传文件 + 真实 Chroma**的配套验证，补充 Phase 2.7 的 MySQL 逻辑备份演练。两者尚未合并为 MySQL/Chroma/上传文件的统一生产恢复流程，也没有覆盖大库、所有权限/索引状态、在线备份、断电或跨设备恢复。只在合成恢复库停用 active；业务设置和现有索引不变。

下一步在独立 MySQL 合成库中组合两种演练：同一次停写窗口记录 SQL dump、上传文件和向量目录的可信清单，恢复后重映射文档路径并复核版本与检索，再准备正式专用库的迁移验收。Graph、ResearchAgent 和前端工作区尚未进入本轮开发。
