import { request } from './client';
import type {
  AdminUserItem,
  ConfigUpdatePayload,
  Paged,
  ResetRequestItem,
  StatsData,
  SystemConfigs,
} from '@/types';

export function listUsers(params: { page?: number; page_size?: number; keyword?: string } = {}) {
  return request<Paged<AdminUserItem>>({ url: '/admin/users', params });
}

export function updateRoleStatus(userId: number, payload: { role?: string; status?: number }) {
  return request<null>({
    url: `/admin/users/${userId}/role-status`,
    method: 'PUT',
    data: payload,
  });
}

/** 生成随机临时密码，并使该用户此前所有 JWT 立即失效 [S-2]。 */
export function resetUserPassword(userId: number) {
  return request<{ temporary_password: string }>({
    url: `/admin/users/${userId}/reset-password`,
    method: 'PUT',
  });
}

export function listResetRequests(includeHandled = false) {
  return request<ResetRequestItem[]>({
    url: '/admin/reset-requests',
    params: { include_handled: includeHandled },
  });
}

/** API Key 以脱敏掩码返回，绝不含明文 [S-1]。 */
export function getConfigs() {
  return request<SystemConfigs>({ url: '/admin/configs' });
}

export function updateConfigs(payload: ConfigUpdatePayload) {
  return request<null>({ url: '/admin/configs', method: 'PUT', data: payload });
}

export function getStats(days = 7) {
  return request<StatsData>({ url: '/admin/stats', params: { days } });
}
