import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import AuthShell from '@/components/AuthShell';
import Spinner from '@/components/Spinner';
import { register } from '@/api/auth';
import { toMessage } from '@/api/client';
import { useToast } from '@/context/ToastContext';

/** 主流邮箱后缀白名单，与后端 ALLOWED_EMAIL_DOMAINS 保持一致（PRD 4.1.1）。 */
const ALLOWED_DOMAINS = [
  'outlook.com',
  'hotmail.com',
  'qq.com',
  'gmail.com',
  '163.com',
  '126.com',
  'foxmail.com',
  'sina.com',
  'yeah.net',
  'edu.cn',
];

const MIN_PASSWORD_LENGTH = 6;

function validate(email: string, password: string, confirm: string): string {
  if (!/^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(email)) {
    return '邮箱格式不符合规范';
  }
  const domain = email.split('@').pop()?.toLowerCase() ?? '';
  if (!ALLOWED_DOMAINS.some((d) => domain === d || domain.endsWith(`.${d}`))) {
    return '暂仅支持主流邮箱注册（如 @outlook.com、@qq.com、@gmail.com、@163.com 等）';
  }
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `密码长度不得少于 ${MIN_PASSWORD_LENGTH} 位`;
  }
  if (password !== confirm) {
    return '两次输入的密码不一致';
  }
  return '';
}

export default function RegisterPage() {
  const navigate = useNavigate();
  const toast = useToast();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    // 前端先行校验，减少无效请求；后端仍会二次校验
    const message = validate(email.trim(), password, confirm);
    setError(message);
    if (message) return;

    setSubmitting(true);
    try {
      await register(email.trim(), password);
      toast.success('注册成功，请登录');
      navigate('/login', { replace: true });
    } catch (err) {
      setError(toMessage(err, '注册失败，请稍后重试'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title="创建账号"
      subtitle="上传你的文献资料，开启可溯源的学术问答"
      footer={
        <>
          已有账号？
          <Link to="/login" className="ml-1 font-medium text-brand-600 hover:underline">
            返回登录
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
          <p className="mt-1 text-xs text-slate-400">
            支持 @outlook.com、@qq.com、@gmail.com、@163.com 等主流邮箱，无需验证码
          </p>
        </div>

        <div>
          <label className="label" htmlFor="password">
            密码
          </label>
          <input
            id="password"
            type="password"
            className="field"
            placeholder={`不少于 ${MIN_PASSWORD_LENGTH} 位`}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <div>
          <label className="label" htmlFor="confirm">
            确认密码
          </label>
          <input
            id="confirm"
            type="password"
            className="field"
            placeholder="请再次输入密码"
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

        <button type="submit" className="btn-primary w-full" disabled={submitting}>
          {submitting && <Spinner />}
          {submitting ? '注册中…' : '注册'}
        </button>
      </form>
    </AuthShell>
  );
}
