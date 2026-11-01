# 三篇论文比较：来源复核展示稿

2026-11-01。此稿由开发Agent逐条检查来源后整理，未经人工验收；不是修改后的正式Artifact。原机器产物保留6条支持，本稿仅展示其中4条，8个单元格待确认。禁止据此直接进行性能排名。

| 论文 | 方法 | 数据集 | 结果 | 局限 |
| --- | --- | --- | --- | --- |
| DPR | 采用基于BERT的双编码器架构，优化嵌入以最大化问题和相关段落向量的内积。 | 待确认：Table 1及相邻文字列有五个数据集；模型声称名称不全，待独立确认误拒，暂不恢复展示。 | 待确认：引文明确有four out of five和absolute EM差1–12；模型否认数字不准确，但中文提高1%–12%仍需澄清绝对百分点与相对提升。 | 待确认：引用选成BERT双编码器方法段，不支持SQuAD较差原因；应修抽取引用匹配。 |
| FID | 该方法通过将问题与检索到的段落和标题连接起来，然后通过编码器独立处理每个段落，最后通过解码器生成答案。 | 待确认：当前引文未支持SQuAD，不能展示完整三数据集声明。 | 待确认：引文明言论文报告的TriviaQA和NaturalQuestions新SOTA；模型否认实验结果，待独立复核，不能解释为今日SOTA。 | 待确认：背景it的前文属于Roberts等人的方法；拒绝展示正确，但模型声称没有参数数量的理由不准确。 |
| REALM | 待确认：PDF第8页引文为概率示例和消融，未支持statement中的优化边缘似然训练目标；撤回展示，不判定论文本身没有该方法。 | 实验在NATURALQUESTIONS-OPEN、WEBQUESTIONS和CURATEDTREC等流行的开放问答基准上进行。 | 待确认：PDF第7页Table 2的38.5/52.0属于REALM(X=CC-News)，原声明漏掉此条件；普通REALM行是38.2/38.5。 | REALM在预训练过程中需要通过整个知识库的检索步骤进行反向传播，这构成了显著的计算挑战。 |

## 展示结论的来源

### DPR / 方法（PDF第2页）

采用基于BERT的双编码器架构，优化嵌入以最大化问题和相关段落向量的内积。

Claim：`claim_f655993b18d47508e7c042b6c8637720608074acb8991408fe43324e0df17968`；Chunk：`chunk_9f420fc859d2a17ac5586b876a2c68507fcc3b733795b48668518920c73991b0`；区间：[0, 572)。

```text
By leveraging the now
standard BERT pretrained model (Devlin et al.,
2019) and a dual-encoder architecture (Bromley
et al., 1994), we focus on developing the right
training scheme using a relatively small number
of question and passage pairs. Through a series
of careful ablation studies, our ﬁnal solution is
surprisingly simple: the embedding is optimized
for maximizing inner products of the question and
relevant passage vectors, with an objective compar-
ing all pairs of questions and passages in a batch.
Our Dense Passage Retriever (DPR) is exception-
ally strong.
```

### FID / 方法（PDF第3页）

该方法通过将问题与检索到的段落和标题连接起来，然后通过编码器独立处理每个段落，最后通过解码器生成答案。

Claim：`claim_415a9347c8b4a1f263d63a20b2edde8af68f2d99180bd3dfc097aeb19816926b`；Chunk：`chunk_89a159d4afec26ad285d27ef340b7380b7e5cb151f2dfc33a15390ff91401ff7`；区间：[0, 551)。

```text
The model takes as input the question, as well as
the support passages, and generates the answer.
More precisely, each retrieved passage and its title
are concatenated with the question, and processed
independently from other passages by the encoder.
We add special tokens question:, title: and
context: before the question, title and text of
each passage. Finally, the decoder performs atten-
1lucene.apache.org
2spacy.io
3github.com/facebookresearch/faiss
tion over the concatenation of the resulting repre-
sentations of all the retrieved passages.
```

### REALM / 数据集（PDF第2页）

实验在NATURALQUESTIONS-OPEN、WEBQUESTIONS和CURATEDTREC等流行的开放问答基准上进行。

Claim：`claim_8fc9bc534baff43a74423b42d2427ddd1982c478f880433a594d034a8bc5a241`；Chunk：`chunk_c13c6a7bcd4c92624a4a042140f4931084760bcd4f51a58985868498009103b6`；区间：[0, 442)。

```text
We evaluate on three popular Open-QA benchmarks
(NATURALQUESTIONS-OPEN, WEBQUESTIONS, and CURAT-
EDTREC) and compare to state-of-the-art Open-QA models,
including both extremely large models that store knowledge
implicitly (such as T5) as well as previous approaches that
also use a knowledge retriever to access external knowledge,
but implement retrieval in a more heuristic fashion (Lee
et al., 2019; Min et al., 2019a; Asai et al., 2019).
```

### REALM / 局限（PDF第2页）

REALM在预训练过程中需要通过整个知识库的检索步骤进行反向传播，这构成了显著的计算挑战。

Claim：`claim_c2b9f059c6957d6178a111df09053a8fe7a68093b1603be4e14818aba42d1275`；Chunk：`chunk_80cbd8afc75917477b7460452d09acdb9424fc63c5556d2ea57038850782e847`；区间：[552, 1633)。

```text
Learning this model end-to-end requires
backpropagating through a retrieval step that considers an
entire corpus of textual knowledge, as shown in Figure 1.
The key intuition of REALM is to train the retriever us-
ing a performance-based signal from unsupervised text:
a retrieval that improves the language model’s perplex-
ity is helpful and should be rewarded, while an un-
informative retrieval should be penalized.
For exam-
ple, in Figure 1, if the model needs to ﬁll the blank
in “the
at the top of the pyramid”, the re-
triever should be rewarded for selecting a document con-
taining “The pyramidion on top allows for less
material higher up the pyramid”. We achieve this
behavior by modeling our retrieve-then-predict approach
as a latent variable language model and optimizing the
marginal likelihood.
Incorporating a large-scale neural retrieval module during
pre-training constitutes a signiﬁcant computational chal-
lenge, since the retriever must consider millions of candi-
date documents for each pre-training step, and we must
backpropagate through its decisions.
```

原始机器结果及12条来源复核见同目录research_context_e2e_20261101.json与research_context_source_review_20261101.json。两条REALM声明只从本展示稿撤回，原始声明、核验判断和Artifact身份均未修改。
