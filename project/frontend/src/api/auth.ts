import { request } from './client';
import type { LoginResult, UserInfo } from '@/types';

export function register(email: string, password: string) {
  return request<{ email: string; created_at: string }>({
    url: '/auth/register',
    method: 'POST',
    data: { email, password },
  });
}

export function login(email: string, password: string) {
  return request<LoginResult>({ url: '/auth/login', method: 'POST', data: { email, password } });
}

/** 提交密码重置申请（同邮箱 10 分钟限 1 次 [M-4]）。 */
export function requestPasswordReset(email: string) {
  return request<null>({ url: '/auth/reset-request', method: 'POST', data: { email } });
}

export function fetchProfile() {
  return request<UserInfo & { status: number; last_login_at: string | null; created_at: string }>({
    url: '/auth/me',
  });
}

/** 修改密码成功后其他设备的 Token 立即失效 [S-2]，此处换发新 Token。 */
export function changePassword(oldPassword: string, newPassword: string) {
  return request<{ access_token: string; token_type: string; expires_in: number }>({
    url: '/auth/change-password',
    method: 'POST',
    data: { old_password: oldPassword, new_password: newPassword },
  });
}
