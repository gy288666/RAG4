import { request } from './client';
import type { DocumentItem, Paged } from '@/types';

export interface ListDocsParams {
  page?: number;
  page_size?: number;
  status?: string;
  keyword?: string;
}

export function listDocuments(params: ListDocsParams = {}) {
  return request<Paged<DocumentItem>>({ url: '/docs/list', params });
}

/** 多文件上传（单文件 ≤50MB，单次 ≤10 个）。 */
export function uploadDocuments(files: File[], onProgress?: (percent: number) => void) {
  const form = new FormData();
  files.forEach((file) => form.append('files', file));
  return request<DocumentItem[]>({
    url: '/docs/upload',
    method: 'POST',
    data: form,
    timeout: 300000,
    onUploadProgress: (event) => {
      if (onProgress && event.total) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    },
  });
}

export function retryDocument(docId: string) {
  return request<DocumentItem>({ url: `/docs/${docId}/retry`, method: 'POST' });
}

export function deleteDocument(docId: string) {
  return request<null>({ url: `/docs/${docId}`, method: 'DELETE' });
}
