/** 全局登录态：Token 与用户信息持久化在 localStorage。 */
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { TOKEN_KEY, USER_KEY } from '@/api/client';
import type { LoginResult, UserInfo } from '@/types';

interface AuthContextValue {
  user: UserInfo | null;
  token: string | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
  signIn: (result: LoginResult) => void;
  signOut: () => void;
  updateToken: (token: string) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readStoredUser(): UserInfo | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as UserInfo) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState<UserInfo | null>(readStoredUser);

  const signIn = useCallback((result: LoginResult) => {
    localStorage.setItem(TOKEN_KEY, result.access_token);
    localStorage.setItem(USER_KEY, JSON.stringify(result.user_info));
    setToken(result.access_token);
    setUser(result.user_info);
  }, []);

  const signOut = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setToken(null);
    setUser(null);
  }, []);

  const updateToken = useCallback((next: string) => {
    localStorage.setItem(TOKEN_KEY, next);
    setToken(next);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      isAuthenticated: Boolean(token),
      isAdmin: user?.role === 'admin',
      signIn,
      signOut,
      updateToken,
    }),
    [user, token, signIn, signOut, updateToken],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth 必须在 AuthProvider 内部使用');
  }
  return context;
}
