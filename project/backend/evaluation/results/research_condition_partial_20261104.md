# 失败任务的部分比较稿

原研究任务仍为failed；本稿只复用成功检查点，其余声明未获语义核验，不代表任务完成。

# 文献比较

比较三篇论文的方法、数据集、结果和局限，注明实验条件；证据不足明确列出，禁止直接性能排名。

| 文献 | 方法 | 数据集 | 结果 | 局限 |
| --- | --- | --- | --- | --- |
| dpr.pdf | 采用基于BERT的双编码器架构，优化嵌入以最大化问题和相关段落向量的内积。 [1] | 待核验 | 待核验 | 待核验 |
| fid.pdf | 该方法通过将问题与检索到的段落和标题连接起来，然后通过编码器独立处理每个段落，最后通过解码器生成答案。 [2] | 待核验 | 待核验 | 待核验 |
| realm.pdf | 待核验 | 待核验 | 待核验 | 待核验 |

引用由原文定位及模型核验；仍需人工复核。实验条件未统一，本表不作性能排名。

引用：
[1] dpr.pdf，PDF 页 2–2，切片 chunk_9f420fc859d2a17ac5586b876a2c68507fcc3b733795b48668518920c73991b0，字符 0:572：By leveraging the now standard BERT pretrained model (Devlin et al., 2019) and a dual-encoder architecture (Bromley et al., 1994), we focus on developing the right training scheme using a relatively small number of question and passage pairs. Through a series of careful ablation studies, our ﬁnal solution is surprisingly simple: the embedding is optimized for maximizing inner products of the question and relevant passage vectors, with an objective compar- ing all pairs of questions and passages in a batch. Our Dense Passage Retriever (DPR) is exception- ally strong.
[2] fid.pdf，PDF 页 3–3，切片 chunk_89a159d4afec26ad285d27ef340b7380b7e5cb151f2dfc33a15390ff91401ff7，字符 0:551：The model takes as input the question, as well as the support passages, and generates the answer. More precisely, each retrieved passage and its title are concatenated with the question, and processed independently from other passages by the encoder. We add special tokens question:, title: and context: before the question, title and text of each passage. Finally, the decoder performs atten- 1lucene.apache.org 2spacy.io 3github.com/facebookresearch/faiss tion over the concatenation of the resulting repre- sentations of all the retrieved passages.

知识缺口：
dpr:dataset:uncertain
dpr:result:uncertain
dpr:limitation:uncertain
fid:dataset:uncertain
fid:result:uncertain
fid:limitation:uncertain
realm:method:uncertain
realm:dataset:uncertain
realm:result:uncertain
realm:limitation:uncertain
