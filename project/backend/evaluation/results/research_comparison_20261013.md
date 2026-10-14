# 文献比较

比较三篇论文的方法、数据集、结果和局限，注明实验条件；证据不足明确列出，禁止直接性能排名。

| 文献 | 方法 | 数据集 | 结果 | 局限 |
| --- | --- | --- | --- | --- |
| dpr.pdf | 该方法使用了BERT预训练模型和双编码器架构。 [1] | 待核验 | DPR在四个数据集上优于之前的SOTA结果，准确率提高了1%到12%。 [2] | SQuAD数据集的性能较低，原因在于问题是在看到段落后由注释者编写的。 [3] |
| fid.pdf | 证据未检出 | 证据未检出 | 证据未检出 | 证据未检出 |
| realm.pdf | 待核验 | 证据未检出 | 待核验 | 证据未检出 |

引用由原文定位及模型核验；仍需人工复核。实验条件未统一，本表不作性能排名。

引用：
[1] dpr.pdf，PDF 页 2–2，切片 chunk_9f420fc859d2a17ac5586b876a2c68507fcc3b733795b48668518920c73991b0，字符 0:242：By leveraging the now standard BERT pretrained model (Devlin et al., 2019) and a dual-encoder architecture (Bromley et al., 1994), we focus on developing the right training scheme using a relatively small number of question and passage pairs.
[2] dpr.pdf，PDF 页 8–8，切片 chunk_f76298a0c6feaf144660c3800efb5acef72d798f5243d3f18bdfb6c079a1c96a，字符 0:173：Overall, our DPR-based models outperform the previous state- of-the-art results on four out of the ﬁve datasets, with 1% to 12% absolute differences in exact match accuracy.
[3] dpr.pdf，PDF 页 5–5，切片 chunk_ae2d1119118d5189767009fd51898013603c626bf9076b2c124fe85214a62a0a，字符 0:587：The results are measured on the de- velopment set of Natural Questions. Our DPR trained using 1,000 examples already outperforms BM25. tiple datasets, TREC, the smallest dataset of the ﬁve, beneﬁts greatly from more training examples. In contrast, Natural Questions and WebQuestions improve modestly and TriviaQA degrades slightly. Results can be improved further in some cases by combining DPR with BM25 in both single- and multi-dataset settings. We conjecture that the lower performance on SQuAD is due to two reasons. First, the annota- tors wrote questions after seeing the passage.

知识缺口：
dpr:dataset:uncertain
fid:method:missing
fid:dataset:missing
fid:result:missing
fid:limitation:missing
realm:method:uncertain
realm:dataset:missing
realm:result:uncertain
realm:limitation:missing


## Publication credit and experiment status

This is an AI-generated partial comparison, not a reviewed synthesis. Numerical verification was replayed offline with recorded model judgments; remaining semantic judgments require human review. This export adds attribution to the canonical artifact Markdown.

Sources: Karpukhin et al., EMNLP 2020, pp. 6769–6781, [DPR](https://aclanthology.org/2020.emnlp-main.550/); Izacard and Grave, EACL 2021, pp. 874–880, [FiD](https://aclanthology.org/2021.eacl-main.74/); Guu, Lee, Tung, Pasupat and Chang, ICML 2020, PMLR 119:3929–3938, [REALM](https://proceedings.mlr.press/v119/guu20a.html). Copyright remains with the respective authors/material owners. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Quotes are extracted from published PDFs; Chinese statements and comparison structure are machine-generated adaptations. No author endorsement is implied. [Source and license notes](../../../docs/research_corpus_sources.md).
