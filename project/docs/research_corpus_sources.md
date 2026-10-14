# 真实文献试点：官方来源与候选证据

核对日期：2026-10-12。范围：DPR、FiD、REALM 三篇正式发表论文。仅用于 RAG4 的小型文献理解试点。

**候选事实、问题及证据定位由 AI 生成，尚待人工审阅；不是人工标注金标准。** 正式冻结前应人工核对完整上下文、表头、限定条件及无答案标签。机器命中短锚点只能证明检索到该位置，不能证明结论受到支持。

## 来源与再分发

| 文档 ID | 正式题名、作者与版本 | 官方入口 | PDF 与页数 |
| --- | --- | --- | --- |
| dpr | Dense Passage Retrieval for Open-Domain Question Answering；Karpukhin 等；EMNLP 2020，6769–6781，DOI 10.18653/v1/2020.emnlp-main.550 | [ACL 正式记录](https://aclanthology.org/2020.emnlp-main.550/) | [官方 PDF](https://aclanthology.org/2020.emnlp-main.550.pdf)，13 页 |
| fid | Leveraging Passage Retrieval with Generative Models for Open Domain Question Answering；Izacard、Grave；EACL 2021，874–880，DOI 10.18653/v1/2021.eacl-main.74 | [ACL 正式记录](https://aclanthology.org/2021.eacl-main.74/) | [官方 PDF](https://aclanthology.org/2021.eacl-main.74.pdf)，7 页 |
| realm | Retrieval Augmented Language Model Pre-Training；Guu、Lee、Tung、Pasupat、Chang；ICML 2020，PMLR 119:3929–3938。PDF 标题带 REALM 前缀。 | [PMLR 正式记录](https://proceedings.mlr.press/v119/guu20a.html) | [官方 PDF](https://proceedings.mlr.press/v119/guu20a/guu20a.pdf)，10 页 |

两篇 ACL 文献发表时间晚于 2016；ACL 官网页脚明确该时期材料适用 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)，并注明各材料的版权归属。[ACL 官方声明](https://aclanthology.org/2020.emnlp-main.550/)

PMLR 的官方出版协议明确授予 CC BY 4.0，并要求署名包含原出版信息及原论文网页链接；作者保留版权。REALM PDF 首页也声明作者版权。这里采用出版方的通用协议作为许可依据，未取得该论文作者签署协议的副本。[PMLR 出版协议](https://proceedings.mlr.press/pmlr-license-agreement.html)、[REALM 官方 PDF](https://proceedings.mlr.press/v119/guu20a/guu20a.pdf#page=1)

因此可在保留署名、来源和许可说明的条件下纳入试点；如果分享抽取文本、译文或标注，应说明这些是衍生内容及发生的修改，不能暗示作者认可。本试点仅取得论文许可依据，不能据此推断其代码、模型或原始数据集的许可。

## 候选事实与定位

下列页码均为 **1-based PDF 页码**，包括正文和参考文献，不能用会议印刷页码代替。锚点是极短原文，匹配前仅合并空白、忽略大小写；个别 PDF 连字需统一。每条事实链接均指向正式 PDF 对应页。阅读整段后才可判断支持关系。

### DPR

| ID | 候选事实 | PDF 页、位置 | 短原文锚点 |
| --- | --- | --- | --- |
| D1 | 独立的 BERT-base uncased 双编码器，以 CLS 输出 768 维表示。 | [3，§3.1 Encoders](https://aclanthology.org/2020.emnlp-main.550.pdf#page=3) | `two independent` |
| D2 | 段落离线编码并由 FAISS 建立索引。 | [3，§3.1 Inference](https://aclanthology.org/2020.emnlp-main.550.pdf#page=3) | `using FAISS` |
| D3 | 最优训练方案结合批内正例复用为负例和一个 BM25 负例。 | [3，§3.2](https://aclanthology.org/2020.emnlp-main.550.pdf#page=3) | `one BM25` |
| D4 | 检索单元为不重叠的 100 词段落，并附文章标题。 | [4，§4.1](https://aclanthology.org/2020.emnlp-main.550.pdf#page=4) | `100 words` |
| D5 | 2018-12-20 英文 Wikipedia 经处理形成 21,015,324 个段落。 | [4，§4.1](https://aclanthology.org/2020.emnlp-main.550.pdf#page=4) | `21,015,324 passages` |
| D6 | Top-k 检索准确率计算前 k 个候选含答案跨度的题目比例。 | [2，§2](https://aclanthology.org/2020.emnlp-main.550.pdf#page=2) | `top-k retrieval accuracy` |
| D7 | 表 2 的 SQuAD 单数据集 Top-20：DPR 63.2，BM25 68.8，不能概括为所有数据集均提升。 | [5，表 2](https://aclanthology.org/2020.emnlp-main.550.pdf#page=5) | `SQuAD` |
| D8 | 表 4 的单数据集 DPR 在 NQ 上端到端 EM 为 41.5。 | [8，表 4](https://aclanthology.org/2020.emnlp-main.550.pdf#page=8) | `Exact Match` |

### FiD

| ID | 候选事实 | PDF 页、位置 | 短原文锚点 |
| --- | --- | --- | --- |
| F1 | 方法可采用 BM25 或 DPR 检索支持段落。 | [3，§3 Retrieval](https://aclanthology.org/2021.eacl-main.74.pdf#page=3) | `BM25` |
| F2 | 每个段落和标题与问题拼接后独立送入编码器。 | [3，§3 Reading](https://aclanthology.org/2021.eacl-main.74.pdf#page=3) | `independently` |
| F3 | 解码器关注拼接后的所有段落表示，融合发生在解码器。 | [3，§3 Reading](https://aclanthology.org/2021.eacl-main.74.pdf#page=3) | `decoder only` |
| F4 | 作者将单段落自注意力与随段落数量线性扩展联系起来。 | [3，§3 Reading](https://aclanthology.org/2021.eacl-main.74.pdf#page=3) | `self attention` |
| F5 | 实验由预训练 T5 初始化；base/large 为 220M/770M 参数。 | [4，Technical details](https://aclanthology.org/2021.eacl-main.74.pdf#page=4) | `770M parameters` |
| F6 | 检索候选为不重叠的 100 词段落。 | [4，Datasets](https://aclanthology.org/2021.eacl-main.74.pdf#page=4) | `100 words` |
| F7 | EM 判定是在规范化后匹配任一参考答案。 | [4，Evaluation](https://aclanthology.org/2021.eacl-main.74.pdf#page=4) | `exact match` |
| F8 | 表 1 的 NQ EM：base 48.2，large 51.4。 | [3，表 1](https://aclanthology.org/2021.eacl-main.74.pdf#page=3) | `Fusion-in-Decoder (large)` |

### REALM

| ID | 候选事实 | PDF 页、位置 | 短原文锚点 |
| --- | --- | --- | --- |
| R1 | 检索器从无监督 MLM 信号学习。 | [1，摘要](https://proceedings.mlr.press/v119/guu20a/guu20a.pdf#page=1) | `masked language modeling` |
| R2 | 掩码偏向命名实体和日期等显著跨度。 | [5，§3.4 Salient span masking](https://proceedings.mlr.press/v119/guu20a/guu20a.pdf#page=5) | `salient spans` |
| R3 | 空文档允许模型在无需检索时分配概率。 | [5，Null document](https://proceedings.mlr.press/v119/guu20a/guu20a.pdf#page=5) | `null document` |
| R4 | 预训练排除掩码句自身所在文档，避免平凡匹配。 | [5，Prohibiting trivial retrievals](https://proceedings.mlr.press/v119/guu20a/guu20a.pdf#page=5) | `trivial candidate` |
| R5 | 检索器采用 ICT 热启动以缓解冷启动。 | [5，Initialization](https://proceedings.mlr.press/v119/guu20a/guu20a.pdf#page=5) | `cold-start problem` |
| R6 | 预训练异步重新编码和索引，降低索引陈旧问题。 | [4，§3.3](https://proceedings.mlr.press/v119/guu20a/guu20a.pdf#page=4) | `asynchronously` |
| R7 | 实验微调时固定文档编码器，只从查询侧更新检索。 | [5，§3.3](https://proceedings.mlr.press/v119/guu20a/guu20a.pdf#page=5) | `query side` |
| R8 | 微调知识库切为最多 288 个 BERT wordpieces 的候选。 | [6，§4.3 Fine-tuning](https://proceedings.mlr.press/v119/guu20a/guu20a.pdf#page=6) | `288 BERT` |

## 20 题构造建议

这是标注设计建议，不是论文作者的实验结论。建议 8 道事实题选 D1/D3/D4/D6/F2/F5/R2/R8；6 道比较题围绕 D1 与 F2 的输入、D3 与 R1 的学习信号、D4/F6/R8 的切分单位、D8 与 F8 的 NQ 结果、D2 与 R6/R7 的索引更新、F3 与 D6 的回答/检索指标区分。

2 道多步题建议：①从各论文输入单元与引用需求推导 RAG4 应记录哪些证据定位信息，答案须标记工程建议；②从各论文训练信号与数据约束分析哪类失败需补检索训练样本、哪类需回答融合，答案须标记推断，不允许说已有 RAG4 实验证实。两题均需至少两个文档的独立支持，并允许合理替代答案。

4 道证据不足题建议：

1. **三方法在同一中文论文比较任务上的准确率分别是多少？** 三篇报告英文开放域 QA；语料内没有所问共同中文任务的实验。检查中文、论文比较、共同任务三个条件，不能拿 NQ 数值代答。
2. **用硅基流动在用户电脑重现三方法，每次请求多少钱？** 所选论文没有该供应商、当前计费和用户硬件测试；即使出现 GPU 资源或训练耗时也不能推算单请求价格。
3. **在完全相同模型规模、检索候选、训练样本和硬件下，哪篇方法显著更好？** 各论文已有各自实验，语料未给这个四条件共同受控比较；不能从不同表格直接推出显著性。
4. **三篇论文报告 Qwen3 作为读者模型时哪个方法最好？** 新模型不属于所选论文实验对象；回答应指出语料缺口及需要的实验，不能依赖模型外部常识补实验数字。

这些标签表示“本试点三篇固定文献不足以支持所问结论”，不是证明整个世界没有答案。人工复核应扫描完整正文、表格及附录，确认所问条件，并记录可能的近似但不满足条件的证据。

## 比较与评测边界

这些是 RAG4 评测设计的约束与推断。数字可用于读取表格的事实题；方法排名必须保留具体行、数据集和指标。特别是 DPR 的 Top-k 检索指标与 EM 不等价，FiD 表 1 的 TriviaQA 有 open/hidden 两列，不能错读；REALM 的 Wikipedia/CC-News 是不同预训练设置。页码命中、关键词出现、结果数字相同均不构成语义支持。

试点比较的是 RAG3/RAG4 对同一固定论文的证据检索与回答，不是复现原论文训练。20 题规模只能发现失败，不能证明统计显著提升，也不足以作为训练集。现阶段应保存 PDF SHA-256、解析器和切分版本、检索及模型配置、逐题候选证据、回答、引用、失败原因和耗时；开发题应与之后真正的留出评测分开。
