import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import AuthShell from '@/components/AuthShell';
import Spinner from '@/components/Spinner';
import { requestPasswordReset } from '@/api/auth';
import { toMessage } from '@/api/client';
import { CheckIcon } from '@/components/Icons';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    if (!email.trim()) {
      setError('请填写注册邮箱');
      return;
    }

    setSubmitting(true);
    try {
      await requestPasswordReset(email.trim());
      setSubmitted(true);
    } catch (err) {
      // 10 分钟内重复提交会被后端拒绝 [M-4]
      setError(toMessage(err, '提交失败，请稍后重试'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title="找回密码"
      subtitle="提交申请后，由管理员为你生成临时密码"
      footer={
        <Link to="/login" className="font-medium text-brand-600 hover:underline">
          返回登录
        </Link>
      }
    >
      {submitted ? (
        <div className="space-y-3 text-center">
          <span className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-moss-100 text-moss-700">
            <CheckIcon className="h-5 w-5" />
          </span>
          <p className="text-sm text-slate-700">
            已提交重置申请，请联系管理员为你重置密码。
          </p>
          <p className="text-xs text-slate-400">
            拿到临时密码后请立即登录并修改密码；修改后其他设备会自动退出登录。
          </p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div>
            <label className="label" htmlFor="email">
              注册邮箱
            </label>
            <input
              id="email"
              type="email"
              className="field"
              placeholder="your-name@outlook.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <p className="mt-1 text-xs text-slate-400">同一邮箱 10 分钟内仅可提交 1 次申请</p>
          </div>

          {error && (
            <p role="alert" className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </p>
          )}

          <button type="submit" className="btn-primary w-full" disabled={submitting}>
            {submitting && <Spinner />}
            {submitting ? '提交中…' : '提交申请'}
          </button>
        </form>
      )}
    </AuthShell>
  );
}
