import { useCallback, useEffect, useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import Spinner, { SkeletonRows } from '@/components/Spinner';
import { FileIcon, UploadIcon } from '@/components/Icons';
import { deleteDocument, listDocuments, retryDocument, uploadDocuments } from '@/api/docs';
import { toMessage } from '@/api/client';
import { useToast } from '@/context/ToastContext';
import type { DocStatus, DocumentItem } from '@/types';
import { formatFileSize, formatRelativeTime } from '@/utils/format';

const MAX_FILE_SIZE = 50 * 1024 * 1024;
const MAX_FILES = 10;
const ACCEPT = '.pdf,.docx,.txt,.md,.markdown';
const PAGE_SIZE = 10;
/** 处理中的文档每 3 秒轮询一次状态（后端 updated_at 可判断是否卡滞 [M-1]） */
const POLL_INTERVAL = 3000;

const STATUS_STYLE: Record<DocStatus, string> = {
  pending: 'bg-slate-100 text-slate-600',
  parsing: 'bg-ochre-100 text-ochre-700',
  vectorizing: 'bg-brand-100 text-brand-700',
  ready: 'bg-moss-100 text-moss-700',
  failed: 'bg-rose-100 text-rose-700',
};

const FILTERS: { value: string; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'ready', label: '已就绪' },
  { value: 'parsing', label: '解析中' },
  { value: 'vectorizing', label: '向量化中' },
  { value: 'failed', label: '失败' },
];

function isProcessing(status: DocStatus) {
  return status === 'pending' || status === 'parsing' || status === 'vectorizing';
}

export default function KnowledgePage() {
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);

  const [items, setItems] = useState<DocumentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [dragging, setDragging] = useState(false);

  const load = useCallback(
    async (options: { silent?: boolean } = {}) => {
      if (!options.silent) setLoading(true);
      try {
        const data = await listDocuments({
          page,
          page_size: PAGE_SIZE,
          status: status || undefined,
          keyword: keyword.trim() || undefined,
        });
        setItems(data.items);
        setTotal(data.total);
      } catch (error) {
        if (!options.silent) toast.error(toMessage(error, '加载文档列表失败'));
      } finally {
        setLoading(false);
      }
    },
    [page, status, keyword, toast],
  );

  useEffect(() => {
    const timer = setTimeout(() => load(), keyword ? 300 : 0);
    return () => clearTimeout(timer);
  }, [load, keyword]);

  // 仅在存在处理中的文档时才轮询，避免无谓请求
  useEffect(() => {
    if (!items.some((item) => isProcessing(item.status))) return;
    const timer = setInterval(() => load({ silent: true }), POLL_INTERVAL);
    return () => clearInterval(timer);
  }, [items, load]);

  const handleFiles = async (files: File[]) => {
    if (files.length === 0) return;
    if (files.length > MAX_FILES) {
      toast.error(`单次最多上传 ${MAX_FILES} 个文件`);
      return;
    }
    const oversized = files.find((file) => file.size > MAX_FILE_SIZE);
    if (oversized) {
      toast.error(`文件「${oversized.name}」超过 50MB 上限`);
      return;
    }

    setUploading(true);
    setProgress(0);
    try {
      await uploadDocuments(files, setProgress);
      toast.success('上传成功，正在后台解析并向量化');
      setPage(1);
      await load({ silent: true });
    } catch (error) {
      toast.error(toMessage(error, '上传失败，请稍后重试'));
    } finally {
      setUploading(false);
      setProgress(0);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const handleInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    handleFiles(Array.from(event.target.files ?? []));
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    handleFiles(Array.from(event.dataTransfer.files));
  };

  const handleRetry = async (item: DocumentItem) => {
    try {
      await retryDocument(item.id);
      toast.success(`已重新提交「${item.file_name}」`);
      await load({ silent: true });
    } catch (error) {
      toast.error(toMessage(error, '重新处理失败，请稍后重试'));
    }
  };

  const handleDelete = async (item: DocumentItem) => {
    if (!window.confirm(`确定删除「${item.file_name}」吗？将同时清理其向量数据。`)) return;
    try {
      await deleteDocument(item.id);
      toast.success('文档已删除');
      await load({ silent: true });
    } catch (error) {
      toast.error(toMessage(error, '删除失败，请稍后重试'));
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-5 px-4 py-6">
        <header>
          <h1 className="heading">我的知识库</h1>
          <p className="mt-1 text-sm text-slate-500">
            支持 PDF、DOCX、TXT、Markdown；单文件最大 50MB，单次最多 10 个。扫描版 PDF
            会自动触发 OCR 识别。
          </p>
        </header>

        {/* 上传区 */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          className={`card flex flex-col items-center justify-center gap-2 border-2 border-dashed px-4 py-8 text-center transition ${
            dragging ? 'border-brand-400 bg-brand-50' : 'border-slate-200'
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPT}
            className="hidden"
            onChange={handleInputChange}
          />
          <UploadIcon className="h-7 w-7 text-slate-400" />
          {uploading ? (
            <div className="w-full max-w-sm">
              <div className="mb-2 flex items-center justify-center gap-2 text-sm text-slate-600">
                <Spinner />
                正在上传 {progress}%
              </div>
              {/* 百分比进度条（PRD 5.4） */}
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
                <div
                  className="h-full rounded-full bg-brand-600 transition-all"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          ) : (
            <>
              <p className="text-sm text-slate-600">拖拽文件到此处，或</p>
              <button
                type="button"
                className="btn-primary"
                onClick={() => inputRef.current?.click()}
              >
                选择文件上传
              </button>
            </>
          )}
        </div>

        {/* 过滤与搜索 */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap gap-1">
            {FILTERS.map((filter) => (
              <button
                key={filter.value}
                type="button"
                onClick={() => {
                  setStatus(filter.value);
                  setPage(1);
                }}
                className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                  status === filter.value
                    ? 'bg-brand-600 text-white'
                    : 'bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50'
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>
          <input
            type="search"
            className="field ml-auto w-full sm:w-56"
            placeholder="搜索文件名…"
            value={keyword}
            onChange={(e) => {
              setKeyword(e.target.value);
              setPage(1);
            }}
            aria-label="搜索文件名"
          />
        </div>

        {/* 文档列表 */}
        <div className="card overflow-hidden">
          {loading ? (
            <SkeletonRows rows={4} />
          ) : items.length === 0 ? (
            <p className="px-4 py-12 text-center text-sm text-slate-400">
              暂无文档，上传后即可开始基于知识库的问答
            </p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {items.map((item) => (
                <li
                  key={item.id}
                  className="flex flex-wrap items-center gap-3 px-4 py-3 transition hover:bg-slate-50"
                >
                  <FileIcon className="h-5 w-5 shrink-0 text-slate-400" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-800">{item.file_name}</p>
                    <p className="mt-0.5 text-xs text-slate-400">
                      {formatFileSize(item.file_size)} · 上传于 {formatRelativeTime(item.created_at)}
                      {isProcessing(item.status) &&
                        ` · 状态更新于 ${formatRelativeTime(item.updated_at)}`}
                    </p>
                  </div>
                  <span
                    className={`badge shrink-0 gap-1 ${STATUS_STYLE[item.status]}`}
                    title={item.status}
                  >
                    {isProcessing(item.status) && <Spinner className="h-3 w-3" />}
                    {item.status_label}
                  </span>
                  {item.status === 'failed' && (
                    <button
                      type="button"
                      onClick={() => handleRetry(item)}
                      className="shrink-0 rounded-md px-2 py-1 text-xs text-brand-600 transition hover:bg-brand-50"
                    >
                      重新处理
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => handleDelete(item)}
                    className="shrink-0 rounded-md px-2 py-1 text-xs text-slate-400 transition hover:bg-rose-50 hover:text-rose-600"
                  >
                    删除
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-3 text-sm">
            <button
              type="button"
              className="btn-ghost"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              上一页
            </button>
            <span className="text-slate-500">
              第 {page} / {totalPages} 页 · 共 {total} 个文档
            </span>
            <button
              type="button"
              className="btn-ghost"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              下一页
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
