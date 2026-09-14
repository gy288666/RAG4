import { useCallback, useEffect, useState } from 'react';
import Modal from '@/components/Modal';
import { SkeletonRows } from '@/components/Spinner';
import { listResetRequests, listUsers, resetUserPassword, updateRoleStatus } from '@/api/admin';
import { toMessage } from '@/api/client';
import { useToast } from '@/context/ToastContext';
import type { AdminUserItem, ResetRequestItem } from '@/types';
import { formatRelativeTime } from '@/utils/format';

const PAGE_SIZE = 20;

export default function AdminUsersPage() {
  const toast = useToast();

  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(true);

  const [requests, setRequests] = useState<ResetRequestItem[]>([]);
  const [tempPassword, setTempPassword] = useState<{ email: string; password: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listUsers({ page, page_size: PAGE_SIZE, keyword: keyword.trim() || undefined });
      setUsers(data.items);
      setTotal(data.total);
    } catch (error) {
      toast.error(toMessage(error, '加载用户列表失败'));
    } finally {
      setLoading(false);
    }
  }, [page, keyword, toast]);

  const loadRequests = useCallback(async () => {
    try {
      setRequests(await listResetRequests());
    } catch {
      /* 待处理申请加载失败不阻塞主列表 */
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(load, keyword ? 300 : 0);
    return () => clearTimeout(timer);
  }, [load, keyword]);

  useEffect(() => {
    loadRequests();
  }, [loadRequests]);

  const handleRoleChange = async (user: AdminUserItem, role: string) => {
    try {
      await updateRoleStatus(user.user_id, { role });
      toast.success('角色已更新');
      await load();
    } catch (error) {
      toast.error(toMessage(error, '更新角色失败'));
    }
  };

  const handleToggleStatus = async (user: AdminUserItem) => {
    const next = user.status === 1 ? 0 : 1;
    try {
      await updateRoleStatus(user.user_id, { status: next });
      toast.success(next === 1 ? '账号已启用' : '账号已禁用');
      await load();
    } catch (error) {
      toast.error(toMessage(error, '更新状态失败'));
    }
  };

  const handleResetPassword = async (user: AdminUserItem) => {
    if (!window.confirm(`确定为「${user.email}」重置密码吗？该用户所有设备将立即退出登录。`)) {
      return;
    }
    try {
      const data = await resetUserPassword(user.user_id);
      setTempPassword({ email: user.email, password: data.temporary_password });
      await loadRequests();
    } catch (error) {
      toast.error(toMessage(error, '重置密码失败'));
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-5 px-4 py-6">
        <header>
          <h1 className="heading">用户管理</h1>
          <p className="mt-1 text-sm text-slate-500">
            查看注册用户、调整角色与启停状态，并处理密码重置申请。
          </p>
        </header>

        {/* 待处理的密码重置申请 */}
        {requests.length > 0 && (
          <section className="card border-ochre-100 bg-ochre-50 p-4">
            <h2 className="mb-2 text-sm font-semibold text-ochre-800">
              待处理的密码重置申请（{requests.length}）
            </h2>
            <ul className="space-y-1.5">
              {requests.map((item) => (
                <li
                  key={item.id}
                  className="flex flex-wrap items-center gap-2 text-sm text-ochre-800"
                >
                  <span className="font-medium">{item.email}</span>
                  <span className="text-xs text-ochre-700">
                    申请于 {formatRelativeTime(item.requested_at)}
                  </span>
                  {item.user_id !== null && (
                    <button
                      type="button"
                      className="ml-auto rounded-md bg-ochre-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-ochre-700"
                      onClick={() =>
                        handleResetPassword({
                          user_id: item.user_id as number,
                          email: item.email,
                        } as AdminUserItem)
                      }
                    >
                      生成临时密码
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        <input
          type="search"
          className="field w-full sm:max-w-xs"
          placeholder="按邮箱搜索用户…"
          value={keyword}
          onChange={(e) => {
            setKeyword(e.target.value);
            setPage(1);
          }}
          aria-label="按邮箱搜索用户"
        />

        <div className="card overflow-hidden">
          {loading ? (
            <SkeletonRows rows={5} />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[46rem] text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">邮箱</th>
                    <th className="px-4 py-3 font-medium">角色</th>
                    <th className="px-4 py-3 font-medium">状态</th>
                    <th className="px-4 py-3 font-medium">文档数</th>
                    <th className="px-4 py-3 font-medium">最近登录</th>
                    <th className="px-4 py-3 font-medium">注册时间</th>
                    <th className="px-4 py-3 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {users.map((user) => (
                    <tr key={user.user_id} className="hover:bg-slate-50">
                      <td className="px-4 py-3 text-slate-800">{user.email}</td>
                      <td className="px-4 py-3">
                        <select
                          className="field py-1 text-xs"
                          value={user.role}
                          onChange={(e) => handleRoleChange(user, e.target.value)}
                          aria-label={`修改 ${user.email} 的角色`}
                        >
                          <option value="user">普通用户</option>
                          <option value="admin">管理员</option>
                        </select>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`badge ${
                            user.status === 1
                              ? 'bg-moss-100 text-moss-700'
                              : 'bg-slate-200 text-slate-600'
                          }`}
                        >
                          {user.status === 1 ? '启用' : '禁用'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-600">{user.doc_count}</td>
                      <td className="px-4 py-3 text-xs text-slate-500">
                        {user.last_login_at ?? '从未登录'}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500">{user.created_at}</td>
                      <td className="px-4 py-3">
                        <div className="flex gap-1.5">
                          <button
                            type="button"
                            onClick={() => handleToggleStatus(user)}
                            className="rounded-md px-2 py-1 text-xs text-slate-600 ring-1 ring-slate-200 hover:bg-slate-100"
                          >
                            {user.status === 1 ? '禁用' : '启用'}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleResetPassword(user)}
                            className="rounded-md px-2 py-1 text-xs text-brand-600 ring-1 ring-brand-200 hover:bg-brand-50"
                          >
                            重置密码
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
              第 {page} / {totalPages} 页 · 共 {total} 位用户
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

      {/* 临时密码只在本次响应中出现一次，需管理员手动转交 */}
      <Modal
        open={Boolean(tempPassword)}
        title="临时密码已生成"
        onClose={() => setTempPassword(null)}
        footer={
          <button type="button" className="btn-primary" onClick={() => setTempPassword(null)}>
            我已记录
          </button>
        }
      >
        {tempPassword && (
          <div className="space-y-3 text-sm">
            <p className="text-slate-600">
              请将以下临时密码手动转交给用户
              <span className="mx-1 font-medium text-slate-800">{tempPassword.email}</span>，
              并提醒其登录后立即修改。
            </p>
            <p className="select-all rounded-lg bg-slate-100 px-4 py-3 text-center font-mono text-base text-slate-900">
              {tempPassword.password}
            </p>
            <p className="text-xs text-rose-600">
              该密码仅显示一次，关闭弹窗后无法再次查看；该用户此前的登录状态已全部失效。
            </p>
          </div>
        )}
      </Modal>
    </div>
  );
}
