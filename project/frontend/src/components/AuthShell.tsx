import type { ReactNode } from 'react';
import { SealMark } from '@/components/Icons';

/** 登录/注册/找回密码的公共外壳布局：暖纸底 + 印章 + 衬线标题，像一页文献的扉页。 */
export default function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="flex min-h-full flex-col bg-slate-50 px-4 py-10">
      {/* 天头粗线：文献扉页式的排版锚点，页面唯一的强调元素 */}
      <div className="mx-auto w-full max-w-md border-t-2 border-brand-600" />
      <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center py-10">
        <div className="mb-6 flex flex-col items-center text-center">
          <SealMark className="h-12 w-12 rounded-lg" textClassName="text-2xl" />
          <h1 className="heading mt-4 text-2xl">{title}</h1>
          <p className="mt-1.5 text-sm text-slate-500">{subtitle}</p>
        </div>
        <div className="card p-6">{children}</div>
        {footer && <div className="mt-4 text-center text-sm text-slate-500">{footer}</div>}
      </div>
    </div>
  );
}
