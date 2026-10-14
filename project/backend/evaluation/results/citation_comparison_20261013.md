# 文献比较

比较三篇论文的方法、数据集、结果和局限，注明实验条件；证据不足明确列出，禁止直接性能排名。

| 文献 | 方法 | 数据集 | 结果 | 局限 |
| --- | --- | --- | --- | --- |
| dpr.pdf | 采用双编码器架构，并优化嵌入以最大化问题和相关段落向量的内积。 [1] | 待核验 | 待核验 | SQuAD数据集的问题缺乏上下文，因为问题是在看到段落后由注释者编写的。 [2] |
| fid.pdf | 该方法在编码器中独立处理段落，在解码器中联合处理，从而能够处理大量段落。 [3] | 待核验 | Fusion-in-Decoder方法在TriviaQA和NaturalQuestions基准测试上取得了新的SOTA结果。 [4] | 待核验 |
| realm.pdf | 待核验 | 待核验 | 待核验 | 待核验 |

引用由原文定位及模型核验；仍需人工复核。实验条件未统一，本表不作性能排名。

引用：
[1] dpr.pdf，PDF 页 2–2，切片 chunk_9f420fc859d2a17ac5586b876a2c68507fcc3b733795b48668518920c73991b0，字符 0:572：By leveraging the now standard BERT pretrained model (Devlin et al., 2019) and a dual-encoder architecture (Bromley et al., 1994), we focus on developing the right training scheme using a relatively small number of question and passage pairs. Through a series of careful ablation studies, our ﬁnal solution is surprisingly simple: the embedding is optimized for maximizing inner products of the question and relevant passage vectors, with an objective compar- ing all pairs of questions and passages in a batch. Our Dense Passage Retriever (DPR) is exception- ally strong.
[2] dpr.pdf，PDF 页 4–4，切片 chunk_5998dffd214e2299963fa640f49cc2e87f15fe295276b3c90a347a56a34bdbd2，字符 0:486：, 2016) is a popu- lar benchmark dataset for reading comprehension. Annotators were presented with a Wikipedia para- graph, and asked to write questions that could be answered from the given text. Although SQuAD has been used previously for open-domain QA re- search, it is not ideal because many questions lack context in absence of the provided paragraph. We still include it in our experiments for providing a fair comparison to previous work and we will discuss more in Section 5.1.
[3] fid.pdf，PDF 页 3–3，切片 chunk_e6227d6e214b5fd71ca1e29c73b6a4db5f377add2938c1c8e2f613d4e4b2577f，字符 0:1509：The model takes as input the question, as well as the support passages, and generates the answer. More precisely, each retrieved passage and its title are concatenated with the question, and processed independently from other passages by the encoder. We add special tokens question:, title: and context: before the question, title and text of each passage. Finally, the decoder performs atten- 1lucene.apache.org 2spacy.io 3github.com/facebookresearch/faiss tion over the concatenation of the resulting repre- sentations of all the retrieved passages. The model thus performs evidence fusion in the decoder only, and we refer to it as Fusion-in-Decoder. By processing passages independently in the en- coder, but jointly in the decoder, this method differs from Min et al. (2020) and Lewis et al. (2020b). Processing passages independently in the encoder allows to scale to large number of contexts, as it only performs self attention over one context at a time. This means that the computation time of the model grows linearly with the number of passages, instead of quadratically. On the other hand, pro- cessing passages jointly in the decoder allows to better aggregate evidence from multiple passages. 4 Experiments In this section, we report empirical evaluations of Fusion-in-Decoder for open domain QA. Datasets. We consider the following datasets, and use the same setting as Lee et al. (2019): • NaturalQuestions (Kwiatkowski et al., 2019) contains questions corresponding to Google search queries.
[4] fid.pdf，PDF 页 2–2，切片 chunk_395c512a9a5b9f2f32e08fd5de3399c2bf9c643061bf2d0f4c67b3d130e2041a，字符 0:574：875 Question + Passage 1 encoder Question + Passage 2 encoder Question + Passage N encoder decoder Answer concat … … … … Figure 2: Architecture of the Fusion-in-Decoder method. representations. Then, a sequence-to-sequence model generates the answer, taking as input the re- trieved passages in addition to the question. While conceptually simple, this method sets new state-of- the-art results on the TriviaQA and NaturalQues- tions benchmarks. In particular, we show that the performance of our method signiﬁcantly improves when the number of retrieved passages increases.

知识缺口：
dpr:dataset:uncertain
dpr:result:uncertain
fid:dataset:uncertain
fid:limitation:uncertain
realm:method:uncertain
realm:dataset:uncertain
realm:result:uncertain
realm:limitation:uncertain


## Publication credit and experiment status

This version uses online citation-handle extraction and model verification, followed by secondary AI source review which demoted two REALM claims. It is still partial, not human reviewed. Raw model decisions and failed attempts are retained in the experiment ledger. This export adds attribution to the canonical artifact Markdown.





Sources: Karpukhin et al., EMNLP 2020, pp. 6769–6781, [DPR](https://aclanthology.org/2020.emnlp-main.550/); Izacard and Grave, EACL 2021, pp. 874–880, [FiD](https://aclanthology.org/2021.eacl-main.74/); Guu, Lee, Tung, Pasupat and Chang, ICML 2020, PMLR 119:3929–3938, [REALM](https://proceedings.mlr.press/v119/guu20a.html). Copyright remains with the respective authors/material owners. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Quotes are extracted from published PDFs; Chinese statements and comparison structure are machine-generated adaptations. No author endorsement is implied. [Source and license notes](../../../docs/research_corpus_sources.md).
