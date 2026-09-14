# Transformer 注意力机制笔记

Transformer 使用缩放点积注意力（Scaled Dot-Product Attention）：

Attention(Q, K, V) = softmax(QK^T / sqrt(d_k)) V

## 多头注意力

多头注意力把查询、键、值投影到多个子空间，再拼接各头输出。
这样做可以让模型同时关注不同位置的不同语义关系。

## 位置编码

原始 Transformer 使用正弦余弦位置编码，使模型能够利用序列顺序信息。
后续工作如 RoPE（旋转位置编码）在长文本场景中表现更好。

关键结论：注意力机制的计算复杂度与序列长度的平方成正比，这是长上下文的主要瓶颈。
