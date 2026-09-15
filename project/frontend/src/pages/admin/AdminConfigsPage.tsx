import { useEffect, useState, type FormEvent } from 'react';
import Spinner, { LoadingBlock } from '@/components/Spinner';
import { getConfigs, updateConfigs } from '@/api/admin';
import { toMessage } from '@/api/client';
import { useToast } from '@/context/ToastContext';
import type { ConfigUpdatePayload, SystemConfigs } from '@/types';

/** 表单态：API Key 输入框始终为空，留空表示“不修改已有 Key” [S-1]。 */
interface FormState {
  llmBaseUrl: string;
  llmModel: string;
  llmAuxModel: string;
  llmApiKey: string;
  rerankApiUrl: string;
  rerankProvider: 'remote' | 'local';
  rerankModel: string;
  rerankVersion: string;
  rerankLocalPath: string;
  rerankTopK: number;
  rerankApiKey: string;
  embeddingModel: string;
  embeddingProvider: 'remote' | 'local';
  embeddingVersion: string;
  embeddingLocalPath: string;
  embeddingBaseUrl: string;
  embeddingApiKey: string;
  chunkSize: number;
  overlap: number;
  topN: number;
  historyRounds: number;
}

function toForm(configs: SystemConfigs): FormState {
  return {
    llmBaseUrl: configs.llm.base_url,
    llmModel: configs.llm.model,
    llmAuxModel: configs.llm.aux_model,
    llmApiKey: '',
    rerankApiUrl: configs.rerank.api_url,
    rerankProvider: configs.rerank.provider,
    rerankModel: configs.rerank.model,
    rerankVersion: configs.rerank.version,
    rerankLocalPath: configs.rerank.local_path,
    rerankTopK: configs.rerank.top_k,
    rerankApiKey: '',
    embeddingModel: configs.embedding.model,
    embeddingProvider: configs.embedding.provider,
    embeddingVersion: configs.embedding.version,
    embeddingLocalPath: configs.embedding.local_path,
    embeddingBaseUrl: configs.embedding.base_url,
    embeddingApiKey: '',
    chunkSize: configs.chunking.chunk_size,
    overlap: configs.chunking.overlap,
    topN: configs.retrieval.top_n,
    historyRounds: configs.retrieval.history_rounds,
  };
}

export default function AdminConfigsPage() {
  const toast = useToast();
  const [configs, setConfigs] = useState<SystemConfigs | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    getConfigs()
      .then((data) => {
        setConfigs(data);
        setForm(toForm(data));
      })
      .catch((err) => toast.error(toMessage(err, '加载系统配置失败')));
  }, [toast]);

  const patch = (changes: Partial<FormState>) =>
    setForm((prev) => (prev ? { ...prev, ...changes } : prev));

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!form) return;
    setError('');

    if (form.overlap >= form.chunkSize) {
      setError('重叠字符数必须小于切片大小');
      return;
    }

    const payload: ConfigUpdatePayload = {
      llm: { base_url: form.llmBaseUrl, model: form.llmModel, aux_model: form.llmAuxModel },
      rerank: {
        provider: form.rerankProvider,
        api_url: form.rerankApiUrl,
        model: form.rerankModel,
        version: form.rerankVersion,
        local_path: form.rerankLocalPath,
        top_k: form.rerankTopK,
      },
      embedding: {
        provider: form.embeddingProvider,
        model: form.embeddingModel,
        version: form.embeddingVersion,
        local_path: form.embeddingLocalPath,
        base_url: form.embeddingBaseUrl,
      },
      chunking: { chunk_size: form.chunkSize, overlap: form.overlap },
      retrieval: { top_n: form.topN, history_rounds: form.historyRounds },
    };
    // 仅在管理员实际填写了新 Key 时才提交，避免清空已有配置
    if (form.llmApiKey.trim()) payload.llm!.api_key = form.llmApiKey.trim();
    if (form.rerankApiKey.trim()) payload.rerank!.api_key = form.rerankApiKey.trim();
    if (form.embeddingApiKey.trim()) payload.embedding!.api_key = form.embeddingApiKey.trim();

    setSaving(true);
    try {
      await updateConfigs(payload);
      const fresh = await getConfigs();
      setConfigs(fresh);
      setForm(toForm(fresh));
      toast.success('配置已保存并立即生效');
    } catch (err) {
      setError(toMessage(err, '保存失败，请稍后重试'));
    } finally {
      setSaving(false);
    }
  };

  if (!form || !configs) {
    return <LoadingBlock text="正在加载系统配置…" />;
  }

  return (
    <div className="h-full overflow-y-auto">
      <form onSubmit={handleSubmit} className="mx-auto max-w-3xl space-y-5 px-4 py-6">
        <header>
          <h1 className="heading">系统配置</h1>
          <p className="mt-1 text-sm text-slate-500">
            修改后立即全局生效。切片参数仅对之后上传的文档生效，不影响历史切片。
          </p>
        </header>

        {/* 大模型 */}
        <section className="card space-y-4 p-5">
          <h2 className="text-sm font-semibold text-slate-700">大模型（OpenAI 兼容接口）</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="llm-base">
                Base URL
              </label>
              <input
                id="llm-base"
                className="field"
                value={form.llmBaseUrl}
                onChange={(e) => patch({ llmBaseUrl: e.target.value })}
                placeholder="https://api.deepseek.com"
              />
            </div>
            <div>
              <label className="label" htmlFor="llm-model">
                模型名称
              </label>
              <input
                id="llm-model"
                className="field"
                value={form.llmModel}
                onChange={(e) => patch({ llmModel: e.target.value })}
                placeholder="deepseek-ai/DeepSeek-V4-Flash"
              />
            </div>
          </div>
          <div>
            <label className="label" htmlFor="llm-aux-model">
              辅助任务模型（问题改写、标题生成）
            </label>
            <input
              id="llm-aux-model"
              className="field"
              value={form.llmAuxModel}
              onChange={(e) => patch({ llmAuxModel: e.target.value })}
              placeholder="留空则复用上方主模型"
            />
            <p className="mt-1 text-xs text-ochre-700">
              主模型为推理型（会先输出思考内容）时建议单独配置一个小模型，
              否则问题改写与标题生成会因思考耗时频繁超时降级。
            </p>
          </div>
          <ApiKeyField
            id="llm-key"
            label="API Key"
            masked={configs.llm.api_key_masked}
            value={form.llmApiKey}
            onChange={(value) => patch({ llmApiKey: value })}
          />
        </section>

        {/* Rerank */}
        <section className="card space-y-4 p-5">
          <h2 className="text-sm font-semibold text-slate-700">Rerank 精排</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="rerank-provider">运行方式</label>
              <select
                id="rerank-provider"
                className="field"
                value={form.rerankProvider}
                onChange={(e) => patch({ rerankProvider: e.target.value as 'remote' | 'local' })}
              >
                <option value="remote">远程兼容接口</option>
                <option value="local">本地微调模型</option>
              </select>
            </div>
            {form.rerankProvider === 'remote' && (
              <div>
                <label className="label" htmlFor="rerank-url">
                  API 终结点
                </label>
                <input
                  id="rerank-url"
                  className="field"
                  value={form.rerankApiUrl}
                  onChange={(e) => patch({ rerankApiUrl: e.target.value })}
                  placeholder="https://api.cohere.com/v1/rerank"
                />
              </div>
            )}
            <div>
              <label className="label" htmlFor="rerank-version">模型版本</label>
              <input
                id="rerank-version"
                className="field"
                value={form.rerankVersion}
                onChange={(e) => patch({ rerankVersion: e.target.value })}
                placeholder="baseline 或 domain-reranker-v1"
              />
            </div>
            {form.rerankProvider === 'local' && (
              <div className="sm:col-span-2">
                <label className="label" htmlFor="rerank-local-path">本地模型目录</label>
                <input
                  id="rerank-local-path"
                  className="field"
                  value={form.rerankLocalPath}
                  onChange={(e) => patch({ rerankLocalPath: e.target.value })}
                  placeholder="models/domain-reranker-v1"
                />
              </div>
            )}
            <div>
              <label className="label" htmlFor="rerank-model">
                模型名称
              </label>
              <input
                id="rerank-model"
                className="field"
                value={form.rerankModel}
                onChange={(e) => patch({ rerankModel: e.target.value })}
                placeholder="BAAI/bge-reranker-v2-m3"
              />
            </div>
            <div>
              <label className="label" htmlFor="rerank-topk">
                精排保留 Top-K
              </label>
              <input
                id="rerank-topk"
                type="number"
                min={1}
                max={50}
                className="field"
                value={form.rerankTopK}
                onChange={(e) => patch({ rerankTopK: Number(e.target.value) })}
              />
            </div>
          </div>
          {form.rerankProvider === 'remote' && (
            <ApiKeyField
              id="rerank-key"
              label="API Key"
              masked={configs.rerank.api_key_masked}
              value={form.rerankApiKey}
              onChange={(value) => patch({ rerankApiKey: value })}
            />
          )}
        </section>

        {/* Embedding */}
        <section className="card space-y-4 p-5">
          <h2 className="text-sm font-semibold text-slate-700">向量化 Embedding</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="embedding-provider">运行方式</label>
              <select
                id="embedding-provider"
                className="field"
                value={form.embeddingProvider}
                onChange={(e) =>
                  patch({ embeddingProvider: e.target.value as 'remote' | 'local' })
                }
              >
                <option value="remote">远程兼容接口</option>
                <option value="local">本地微调模型</option>
              </select>
            </div>
            <div>
              <label className="label" htmlFor="embedding-model">
                模型名称
              </label>
              <input
                id="embedding-model"
                className="field"
                value={form.embeddingModel}
                onChange={(e) => patch({ embeddingModel: e.target.value })}
                placeholder="Qwen/Qwen3-Embedding-8B"
              />
            </div>
            <div>
              <label className="label" htmlFor="embedding-version">模型/索引版本</label>
              <input
                id="embedding-version"
                className="field"
                value={form.embeddingVersion}
                onChange={(e) => patch({ embeddingVersion: e.target.value })}
                placeholder="baseline 或 domain-embedding-v1"
              />
            </div>
            {form.embeddingProvider === 'local' && (
              <div className="sm:col-span-2">
                <label className="label" htmlFor="embedding-local-path">本地模型目录</label>
                <input
                  id="embedding-local-path"
                  className="field"
                  value={form.embeddingLocalPath}
                  onChange={(e) => patch({ embeddingLocalPath: e.target.value })}
                  placeholder="models/domain-embedding-v1"
                />
              </div>
            )}
            {form.embeddingProvider === 'remote' && (
              <div>
                <label className="label" htmlFor="embedding-base">
                  Base URL（留空则复用大模型地址）
                </label>
                <input
                  id="embedding-base"
                  className="field"
                  value={form.embeddingBaseUrl}
                  onChange={(e) => patch({ embeddingBaseUrl: e.target.value })}
                />
              </div>
            )}
          </div>
          {form.embeddingProvider === 'remote' && (
            <ApiKeyField
              id="embedding-key"
              label="API Key（留空则复用大模型 Key）"
              masked={configs.embedding.api_key_masked}
              value={form.embeddingApiKey}
              onChange={(value) => patch({ embeddingApiKey: value })}
            />
          )}
          <p className="text-xs text-ochre-700">
            更换 Embedding Adapter 或模型时必须填写新的版本；系统会写入独立索引，
            避免不同向量空间混用。新版本需要重新构建文档索引。
          </p>
        </section>

        {/* 切片与检索 */}
        <section className="card space-y-4 p-5">
          <h2 className="text-sm font-semibold text-slate-700">切片与检索参数</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="chunk-size">
                切片大小（字符）
              </label>
              <input
                id="chunk-size"
                type="number"
                min={100}
                max={4000}
                className="field"
                value={form.chunkSize}
                onChange={(e) => patch({ chunkSize: Number(e.target.value) })}
              />
            </div>
            <div>
              <label className="label" htmlFor="overlap">
                重叠字符数
              </label>
              <input
                id="overlap"
                type="number"
                min={0}
                max={1000}
                className="field"
                value={form.overlap}
                onChange={(e) => patch({ overlap: Number(e.target.value) })}
              />
            </div>
            <div>
              <label className="label" htmlFor="top-n">
                向量检索候选数 Top-N
              </label>
              <input
                id="top-n"
                type="number"
                min={1}
                max={100}
                className="field"
                value={form.topN}
                onChange={(e) => patch({ topN: Number(e.target.value) })}
              />
            </div>
            <div>
              <label className="label" htmlFor="history-rounds">
                多轮对话历史轮数上限
              </label>
              <input
                id="history-rounds"
                type="number"
                min={0}
                max={20}
                className="field"
                value={form.historyRounds}
                onChange={(e) => patch({ historyRounds: Number(e.target.value) })}
              />
            </div>
          </div>
        </section>

        {error && (
          <p role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {error}
          </p>
        )}

        <div className="flex justify-end">
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving && <Spinner />}
            {saving ? '保存中…' : '保存配置'}
          </button>
        </div>
      </form>
    </div>
  );
}

/** API Key 输入框：只展示脱敏掩码，留空表示不修改。 */
function ApiKeyField({
  id,
  label,
  masked,
  value,
  onChange,
}: {
  id: string;
  label: string;
  masked: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        type="password"
        className="field"
        autoComplete="new-password"
        placeholder={masked ? `当前：${masked}（留空则不修改）` : '尚未配置，请填写'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <p className="mt-1 text-xs text-slate-400">
        Key 以 AES-256 加密存储，接口仅返回脱敏掩码，永不回传明文。
      </p>
    </div>
  );
}
