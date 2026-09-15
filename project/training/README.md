# RAG4 模型微调工作流

本目录把模型微调作为独立实验闭环接入 RAG4。在线服务只依赖
`backend/app/modeling` 中的小接口；训练框架、数据处理和模型权重不会侵入
`rag_service.py`。

## 优先顺序

1. **Reranker 微调（P1，先做）**：直接优化候选片段排序，训练数据少、回滚简单，
   最容易用 MRR/nDCG 证明收益。
2. **Embedding 对比学习（P1）**：召回率仍不足时再做；上线必须使用新的
   `embedding.version` 并重建索引。
3. **Artifact/Graph LoRA-SFT（P2）**：证据链和输出格式稳定后再训练生成模型，
   避免把流程缺陷学进模型。

## 1. Conda 环境

项目固定使用 Python 3.11。仓库当前开发环境为 `rag4-py3.11`：

```powershell
conda activate rag4-py3.11
python -m pip install -r training/requirements.txt
```

模型训练建议使用带 CUDA 的 PyTorch；CPU 可以验证脚本，但不适合正式训练。

## 2. 数据约定与硬负样本

候选输入为 JSONL，每行代表一个检索问题。`label=true` 的候选是人工确认的证据，
`label=false` 且基线分数较高的候选会被当作 hard negative：

```json
{"query_id":"q001","query":"RAG 如何降低幻觉？","candidates":[{"id":"c1","text":"有依据的正例","label":true,"score":0.91},{"id":"c2","text":"语义相似但不回答问题","label":false,"score":0.89}]}
```

不要默认把用户聊天内容拿去训练。训练集应来自公开评测集、项目自建题或用户明确
授权并脱敏的数据，并保留 train/dev/test 隔离。

```powershell
python training/datasets/build_retrieval_dataset.py `
  --input training/data/judged_candidates.jsonl `
  --output-dir training/data/generated `
  --max-negatives 4
```

输出：

- `embedding_train.jsonl`：`anchor / positive / negative` 三元组；
- `reranker_train.jsonl`：`query / passage / label` 二分类样本；
- `ranking_eval.jsonl`：供 Recall@K、MRR、nDCG 离线评测。

## 3. 训练 Reranker（推荐先跑）

```powershell
python training/reranker/train.py `
  --train-data training/data/generated/reranker_train.jsonl `
  --base-model BAAI/bge-reranker-base `
  --output-dir models/domain-reranker-v1 `
  --epochs 2 --batch-size 8 --learning-rate 2e-5 `
  --lora-rank 16 --fp16
```

训练完成后，在管理后台选择 `local`，本地路径填写
`models/domain-reranker-v1`，版本填写 `domain-reranker-v1`。Reranker 切换不要求
重建向量索引。

## 4. 训练 Embedding

```powershell
python training/embedding/train.py `
  --train-data training/data/generated/embedding_train.jsonl `
  --base-model BAAI/bge-small-zh-v1.5 `
  --output-dir models/domain-embedding-v1 `
  --epochs 2 --batch-size 16 --learning-rate 2e-5 `
  --lora-rank 16 --fp16
```

上线时必须把 `embedding.version` 改成新值。RAG4 会把新版本写入独立 Chroma
Collection，旧索引不会与新向量空间混写；随后应显式重建文档索引。当前基线没有
批量重建 API，因此开发期可重新上传评测文档，正式版本按开发计划补异步重建任务。

## 5. LoRA-SFT 训练图谱抽取或研究产物模型

输入 JSONL 每行包含 `messages`（OpenAI chat 格式），或已经套好模板的 `text`：

```powershell
python training/sft/train_lora.py `
  --train-data training/data/artifact_sft.jsonl `
  --base-model Qwen/Qwen2.5-7B-Instruct `
  --output-dir models/artifact-composer-lora-v1 `
  --epochs 2 --batch-size 1 --gradient-accumulation-steps 16 --fp16
```

此脚本输出 LoRA Adapter。可用 vLLM、SGLang 或兼容服务加载后，通过现有
OpenAI-compatible LLM 配置接入；不要在证据门禁之前直接替换事实校验逻辑。

## 6. 评测与上线门禁

将某个模型版本的检索结果保存为以下 JSONL：

```json
{"query_id":"q001","relevant_ids":["c1"],"ranked_ids":["c2","c1","c3"]}
```

```powershell
python training/evaluation/evaluate_ranking.py `
  --input training/data/results/domain-reranker-v1.jsonl `
  --k 1 5 10 `
  --output training/outputs/domain-reranker-v1-metrics.json
```

只有在冻结测试集上 Recall@K、MRR 或 nDCG 有可解释提升，且延迟、失败率可接受时，
才切换生产配置。每份结果应同时记录：代码提交、基础模型、训练数据版本、模型版本、
索引版本和推理参数。
