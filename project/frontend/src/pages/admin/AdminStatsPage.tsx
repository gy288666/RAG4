import { useEffect, useState } from 'react';
import { LoadingBlock } from '@/components/Spinner';
import { getStats } from '@/api/admin';
import { toMessage } from '@/api/client';
import { useToast } from '@/context/ToastContext';
import type { StatsData } from '@/types';

const RANGES = [
  { value: 1, label: '今日' },
  { value: 7, label: '近 7 天' },
  { value: 30, label: '近 30 天' },
];

function formatNumber(value: number): string {
  return value.toLocaleString('zh-CN');
}

export default function AdminStatsPage() {
  const toast = useToast();
  const [days, setDays] = useState(7);
  const [stats, setStats] = useState<StatsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getStats(days)
      .then((data) => {
        if (!cancelled) setStats(data);
      })
      .catch((error) => {
        if (!cancelled) toast.error(toMessage(error, '加载监控数据失败'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [days, toast]);

  const maxDaily = Math.max(1, ...(stats?.daily_trend.map((d) => d.count) ?? [1]));

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-5 px-4 py-6">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="heading">运行监控</h1>
            <p className="mt-1 text-sm text-slate-500">
              统计大模型调用量、Token 消耗、失败率与 OCR 失败队列。
            </p>
          </div>
          <div className="flex gap-1">
            {RANGES.map((range) => (
              <button
                key={range.value}
                type="button"
                onClick={() => setDays(range.value)}
                className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                  days === range.value
                    ? 'bg-brand-600 text-white'
                    : 'bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50'
                }`}
              >
                {range.label}
              </button>
            ))}
          </div>
        </header>

        {loading || !stats ? (
          <LoadingBlock text="正在加载监控数据…" />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatCard label="大模型调用次数" value={formatNumber(stats.total_llm_calls)} />
              <StatCard label="Token 消耗量" value={formatNumber(stats.total_tokens_used)} />
              <StatCard label="Rerank 调用" value={formatNumber(stats.total_rerank_calls)} />
              <StatCard label="向量检索次数" value={formatNumber(stats.total_vector_searches)} />
              <StatCard label="OCR 处理次数" value={formatNumber(stats.total_ocr_calls)} />
              <StatCard label="总调用次数" value={formatNumber(stats.total_calls)} />
              <StatCard label="失败次数" value={formatNumber(stats.failure_count)} tone="danger" />
              <StatCard label="失败率" value={stats.failure_rate} tone="danger" />
            </div>

            {/*
              每日调用趋势（纯 CSS 柱状图，无需额外图表库）。
              外层用 items-stretch 让每列撑满 h-40，柱体的百分比高度才有参照基准；
              若用 items-end，列高会塌缩成内容高度，柱子将不可见。
            */}
            <section className="card p-5">
              <h2 className="mb-4 text-sm font-semibold text-slate-700">每日调用趋势</h2>
              {stats.daily_trend.length === 0 ? (
                <p className="py-6 text-center text-sm text-slate-400">该时间范围内暂无调用记录</p>
              ) : (
                <div className="flex h-44 items-stretch gap-2 overflow-x-auto">
                  {stats.daily_trend.map((item) => (
                    <div
                      key={item.date}
                      className="flex min-w-10 flex-1 flex-col items-center gap-1.5"
                      title={`${item.date}：${item.count} 次`}
                    >
                      <span className="text-[10px] text-slate-400">{item.count}</span>
                      {/* 柱体轨道：flex-1 拿到确定高度，柱体绝对定位贴底生长 */}
                      <div className="relative w-full flex-1">
                        <div
                          className="absolute inset-x-0 bottom-0 rounded-t bg-brand-500 transition-all"
                          style={{ height: `${Math.max(4, (item.count / maxDaily) * 100)}%` }}
                        />
                      </div>
                      <span className="text-[10px] text-slate-400">{item.date.slice(5)}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="card overflow-hidden">
              <h2 className="border-b border-slate-100 px-5 py-4 text-sm font-semibold text-slate-700">
                文档处理 / OCR 失败队列
              </h2>
              {stats.ocr_failed_queue.length === 0 ? (
                <p className="px-5 py-10 text-center text-sm text-slate-400">
                  暂无失败记录，系统运行正常
                </p>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {stats.ocr_failed_queue.map((item) => (
                    <li key={`${item.doc_id}-${item.created_at}`} className="px-5 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium text-slate-800">{item.file_name}</span>
                        <span className="text-xs text-slate-400">{item.created_at}</span>
                      </div>
                      <p className="mt-1 text-xs text-rose-600">{item.error}</p>
                      <p className="mt-0.5 font-mono text-[11px] text-slate-300">{item.doc_id}</p>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  tone = 'default',
}: {
  label: string;
  value: string;
  tone?: 'default' | 'danger';
}) {
  return (
    <div className="card p-4">
      <p className="text-xs text-slate-400">{label}</p>
      <p
        className={`mt-1.5 font-mono text-2xl font-semibold tabular-nums ${
          tone === 'danger' ? 'text-rose-600' : 'text-slate-900'
        }`}
      >
        {value}
      </p>
    </div>
  );
}
