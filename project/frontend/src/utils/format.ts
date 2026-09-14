/** 通用格式化工具。 */

export function formatFileSize(bytes: number): string {
  if (!bytes || bytes < 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

/** 相对时间：用于会话列表与文档列表的轻量时间展示。 */
export function formatRelativeTime(value: string | null): string {
  if (!value) return '—';
  const target = new Date(value.replace(/-/g, '/'));
  if (Number.isNaN(target.getTime())) return value;

  const diff = Date.now() - target.getTime();
  const minute = 60_000;
  if (diff < minute) return '刚刚';
  if (diff < 60 * minute) return `${Math.floor(diff / minute)} 分钟前`;
  if (diff < 24 * 60 * minute) return `${Math.floor(diff / (60 * minute))} 小时前`;
  if (diff < 7 * 24 * 60 * minute) return `${Math.floor(diff / (24 * 60 * minute))} 天前`;
  return value.slice(0, 10);
}

/**
 * 拆分模型回答的正文与末尾的「参考来源」纯文本块。
 *
 * 提示词要求模型在答案末尾输出引用清单（PRD 附录 A），而前端会用可交互的
 * 引用卡片替代展示，因此把这段纯文本单独剥离，避免同样的内容出现两次。
 */
export function splitAnswer(content: string): { body: string; references: string } {
  const match = content.match(/\n-{2,}\s*\n?\s*参考来源[：:]/);
  if (match?.index !== undefined) {
    return {
      body: content.slice(0, match.index).trimEnd(),
      references: content.slice(match.index).trim(),
    };
  }
  const plain = content.match(/\n\s*参考来源[：:]/);
  if (plain?.index !== undefined) {
    return {
      body: content.slice(0, plain.index).trimEnd(),
      references: content.slice(plain.index).trim(),
    };
  }
  return { body: content, references: '' };
}

/** 引用定位描述 [I-3]：PDF 用页码，其余用切片序号。 */
export function citationLocator(page: number | null, chunkIndex: number): string {
  return page !== null && page !== undefined ? `第 ${page} 页` : `第 ${chunkIndex + 1} 个片段`;
}

/** 降级告警的中文文案 [M-6]。 */
export const WARNING_LABELS: Record<string, string> = {
  rerank_timeout: '云端精排服务超时，本次已直接使用向量检索结果',
};
