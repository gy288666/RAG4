import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import AuthShell from '@/components/AuthShell';
import Spinner from '@/components/Spinner';
import { login } from '@/api/auth';
import { toMessage } from '@/api/client';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';

export default function LoginPage() {
  const { isAuthenticated, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (isAuthenticated) {
    return <Navigate to="/chat" replace />;
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');

    if (!email.trim() || !password) {
      setError('请填写邮箱与密码');
      return;
    }

    setSubmitting(true);
    try {
      const result = await login(email.trim(), password);
      signIn(result);
      toast.success('登录成功');
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from && !from.startsWith('/login') ? from : '/chat', { replace: true });
    } catch (err) {
      // 后端会区分“邮箱未注册”与“密码错误”
      setError(toMessage(err, '登录失败，请稍后重试'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title="欢迎回来"
      subtitle="登录后即可管理个人知识库并开始学术问答"
      footer={
        <>
          还没有账号？
          <Link to="/register" className="ml-1 font-medium text-brand-600 hover:underline">
            立即注册
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <div>
          <label className="label" htmlFor="email">
            邮箱
          </label>
          <input
            id="email"
            type="email"
            className="field"
            placeholder="your-name@outlook.com"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div>
          <label className="label" htmlFor="password">
            密码
          </label>
          <input
            id="password"
            type="password"
            className="field"
            placeholder="请输入密码"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {error && (
          <p role="alert" className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {error}
          </p>
        )}

        <button type="submit" className="btn-primary w-full" disabled={submitting}>
          {submitting && <Spinner />}
          {submitting ? '登录中…' : '登录'}
        </button>

        <div className="text-right">
          <Link to="/forgot-password" className="text-sm text-slate-500 hover:text-brand-600">
            忘记密码？
          </Link>
        </div>
      </form>
    </AuthShell>
  );
}
