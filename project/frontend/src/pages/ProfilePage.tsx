import { useEffect, useState, type FormEvent } from 'react';
import Spinner from '@/components/Spinner';
import { changePassword, fetchProfile } from '@/api/auth';
import { toMessage } from '@/api/client';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';

export default function ProfilePage() {
  const { user, isAdmin, updateToken } = useAuth();
  const toast = useToast();

  const [profile, setProfile] = useState<{ last_login_at: string | null; created_at: string } | null>(
    null,
  );
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchProfile()
      .then((data) => setProfile({ last_login_at: data.last_login_at, created_at: data.created_at }))
      .catch(() => setProfile(null));
  }, []);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');

    if (newPassword.length < 6) {
      setError('新密码长度不得少于 6 位');
      return;
    }
    if (newPassword !== confirm) {
      setError('两次输入的新密码不一致');
      return;
    }

    setSubmitting(true);
    try {
      const data = await changePassword(oldPassword, newPassword);
      // 后端换发新 Token，当前设备无需重新登录；其他设备的旧 Token 立即失效 [S-2]
      updateToken(data.access_token);
      setOldPassword('');
      setNewPassword('');
      setConfirm('');
      toast.success('密码修改成功，其他设备需重新登录');
    } catch (err) {
      setError(toMessage(err, '修改失败，请稍后重试'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-2xl space-y-5 px-4 py-6">
        <header>
          <h1 className="heading">个人设置</h1>
        </header>

        <section className="card p-5">
          <h2 className="mb-4 text-sm font-semibold text-slate-700">账号信息</h2>
          <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-slate-400">邮箱</dt>
              <dd className="mt-0.5 text-slate-800">{user?.email}</dd>
            </div>
            <div>
              <dt className="text-slate-400">角色</dt>
              <dd className="mt-0.5 text-slate-800">{isAdmin ? '系统管理员' : '普通用户'}</dd>
            </div>
            <div>
              <dt className="text-slate-400">注册时间</dt>
              <dd className="mt-0.5 text-slate-800">{profile?.created_at ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-slate-400">最近登录</dt>
              <dd className="mt-0.5 text-slate-800">{profile?.last_login_at ?? '—'}</dd>
            </div>
          </dl>
        </section>

        <section className="card p-5">
          <h2 className="mb-1 text-sm font-semibold text-slate-700">修改密码</h2>
          <p className="mb-4 text-xs text-slate-400">
            若你使用管理员下发的临时密码登录，请立即在此修改。修改后其他设备上的登录状态会立即失效。
          </p>
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div>
              <label className="label" htmlFor="old-password">
                原密码
              </label>
              <input
                id="old-password"
                type="password"
                className="field"
                autoComplete="current-password"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
              />
            </div>
            <div>
              <label className="label" htmlFor="new-password">
                新密码
              </label>
              <input
                id="new-password"
                type="password"
                className="field"
                placeholder="不少于 6 位"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </div>
            <div>
              <label className="label" htmlFor="confirm-password">
                确认新密码
              </label>
              <input
                id="confirm-password"
                type="password"
                className="field"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </div>

            {error && (
              <p role="alert" className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {error}
              </p>
            )}

            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting && <Spinner />}
              {submitting ? '提交中…' : '确认修改'}
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
