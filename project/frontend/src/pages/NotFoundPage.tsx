import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-3 px-4 text-center">
      {/* 用排版而非图标承担 404 的视觉：等宽大字 + 衬线说明 */}
      <p className="font-mono text-5xl font-semibold tracking-tight text-brand-600">404</p>
      <h1 className="heading">页面不存在</h1>
      <p className="text-sm text-slate-500">你访问的地址可能已被移动或删除。</p>
      <Link to="/chat" className="btn-primary mt-2">
        返回问答页
      </Link>
    </div>
  );
}
