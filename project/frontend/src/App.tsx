import { Navigate, Route, Routes } from 'react-router-dom';
import AppLayout from '@/components/AppLayout';
import ProtectedRoute from '@/components/ProtectedRoute';
import LoginPage from '@/pages/LoginPage';
import RegisterPage from '@/pages/RegisterPage';
import ForgotPasswordPage from '@/pages/ForgotPasswordPage';
import ChatPage from '@/pages/ChatPage';
import KnowledgePage from '@/pages/KnowledgePage';
import ProfilePage from '@/pages/ProfilePage';
import AdminUsersPage from '@/pages/admin/AdminUsersPage';
import AdminConfigsPage from '@/pages/admin/AdminConfigsPage';
import AdminStatsPage from '@/pages/admin/AdminStatsPage';
import NotFoundPage from '@/pages/NotFoundPage';

export default function App() {
  return (
    <Routes>
      {/* 公开页面 */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />

      {/* 需登录 */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:sessionId" element={<ChatPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/profile" element={<ProfilePage />} />

          {/* 需管理员角色 */}
          <Route element={<ProtectedRoute requireAdmin />}>
            <Route path="/admin/users" element={<AdminUsersPage />} />
            <Route path="/admin/configs" element={<AdminConfigsPage />} />
            <Route path="/admin/stats" element={<AdminStatsPage />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
