import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import {
  ChartIcon,
  ChatIcon,
  CloseIcon,
  LibraryIcon,
  LogoutIcon,
  MenuIcon,
  SealMark,
  SlidersIcon,
  UsersIcon,
} from '@/components/Icons';

const NAV_ITEMS = [
  { to: '/chat', label: '智能问答', icon: ChatIcon, adminOnly: false },
  { to: '/knowledge', label: '我的知识库', icon: LibraryIcon, adminOnly: false },
  { to: '/admin/users', label: '用户管理', icon: UsersIcon, adminOnly: true },
  { to: '/admin/configs', label: '系统配置', icon: SlidersIcon, adminOnly: true },
  { to: '/admin/stats', label: '运行监控', icon: ChartIcon, adminOnly: true },
];

/** 应用主框架：桌面端固定侧边栏，移动端抽屉式导航（PRD 5.4 响应式）。 */
export default function AppLayout() {
  const { user, isAdmin, signOut } = useAuth();
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const items = NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin);

  const handleSignOut = () => {
    signOut();
    navigate('/login', { replace: true });
  };

  const brand = (
    <div className="flex items-center gap-2.5">
      <SealMark />
      <span className="font-serif text-base font-semibold tracking-wide text-slate-900">
        学术知识引擎
      </span>
    </div>
  );

  const nav = (
    <nav className="flex flex-1 flex-col gap-0.5 p-3">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          onClick={() => setDrawerOpen(false)}
          className={({ isActive }) =>
            `relative flex items-center gap-2.5 rounded-md px-3 py-2.5 text-sm font-medium transition-colors ${
              isActive
                ? 'bg-brand-50 text-brand-700 shadow-[inset_2px_0_0_#1f3a5f]'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            }`
          }
        >
          <item.icon className="h-4 w-4" />
          {item.label}
        </NavLink>
      ))}
    </nav>
  );

  const footer = (
    <div className="border-t border-slate-200 p-3">
      <NavLink
        to="/profile"
        onClick={() => setDrawerOpen(false)}
        className="mb-2 flex items-center gap-3 rounded-md px-3 py-2 transition hover:bg-slate-100"
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-600 text-sm font-serif font-semibold text-white">
          {user?.email?.[0]?.toUpperCase() ?? 'U'}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm text-slate-700">{user?.email}</span>
          <span className="block text-xs text-slate-400">
            {isAdmin ? '系统管理员' : '普通用户'}
          </span>
        </span>
      </NavLink>
      <button
        type="button"
        onClick={handleSignOut}
        className="btn-ghost w-full [&>svg]:text-slate-400"
      >
        <LogoutIcon />
        退出登录
      </button>
    </div>
  );

  return (
    <div className="flex h-full">
      {/* 桌面端侧边栏 */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white lg:flex">
        <div className="border-b border-slate-200 px-4 py-4">{brand}</div>
        {nav}
        {footer}
      </aside>

      {/* 移动端抽屉 */}
      {drawerOpen && (
        <div className="fixed inset-0 z-30 lg:hidden">
          <div
            className="absolute inset-0 bg-slate-900/40"
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
          <aside className="animate-fade-in relative flex h-full w-64 flex-col bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-4">
              {brand}
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                aria-label="关闭菜单"
                className="p-1 text-slate-400"
              >
                <CloseIcon />
              </button>
            </div>
            {nav}
            {footer}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="打开菜单"
            className="rounded-md p-1.5 text-slate-600 hover:bg-slate-100"
          >
            <MenuIcon />
          </button>
          {brand}
        </header>
        <main className="min-h-0 flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
