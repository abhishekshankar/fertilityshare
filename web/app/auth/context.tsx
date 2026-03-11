"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

type User = { id: string; email: string; invite_allowed: boolean };

type AuthState = {
  token: string | null;
  user: User | null;
  loading: boolean;
  signIn: (token: string) => void;
  signOut: () => void;
  setTokenFromCallback: (token: string) => void;
};

const AuthContext = createContext<AuthState | null>(null);

const TOKEN_KEY = "syllabus_token";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchUser = useCallback(async (t: string) => {
    setLoading(true);
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 8000);
      const res = await fetch("/api/v1/auth/me", {
        headers: { Authorization: `Bearer ${t}` },
        cache: "no-store",
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      if (process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DEBUG_INGEST === "1") {
        fetch("http://127.0.0.1:7783/ingest/cc850ea7-3322-438b-a856-c76e4d0f2158", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "41ee7a" },
          body: JSON.stringify({
            sessionId: "41ee7a",
            location: "auth/context.tsx:fetchUser",
            message: "fetchUser_result",
            data: { status: res.status, ok: res.ok },
            timestamp: Date.now(),
            hypothesisId: "H3",
          }),
        }).catch(() => {});
      }
      if (res.ok) {
        const data = await res.json();
        setUser({ id: data.id, email: data.email, invite_allowed: data.invite_allowed ?? false });
      } else {
        setUser(null);
        setToken(null);
        if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
      }
    } catch (e) {
      if (
        typeof window !== "undefined" &&
        process.env.NODE_ENV === "development" &&
        process.env.NEXT_PUBLIC_DEBUG_INGEST === "1"
      ) {
        fetch("http://127.0.0.1:7783/ingest/cc850ea7-3322-438b-a856-c76e4d0f2158", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "41ee7a" },
          body: JSON.stringify({
            sessionId: "41ee7a",
            location: "auth/context.tsx:fetchUser",
            message: "fetchUser_catch",
            data: { err: String(e) },
            timestamp: Date.now(),
            hypothesisId: "H3",
          }),
        }).catch(() => {});
      }
      setUser(null);
      setToken(null);
      if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const stored = typeof window !== "undefined" ? window.localStorage.getItem(TOKEN_KEY) : null;
    if (stored) {
      setToken(stored);
      fetchUser(stored).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
    // Safety: stop showing loading if still true after 10s (e.g. hydration or network issue)
    const fallback = setTimeout(() => setLoading(false), 10000);
    return () => clearTimeout(fallback);
  }, [fetchUser]);

  const signIn = useCallback((t: string) => {
    if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, t);
    setToken(t);
    fetchUser(t);
  }, [fetchUser]);

  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
    if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
  }, []);

  const setTokenFromCallback = useCallback((t: string) => {
    if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, t);
    setToken(t);
    fetchUser(t);
  }, [fetchUser]);

  const value: AuthState = {
    token,
    user,
    loading,
    signIn,
    signOut,
    setTokenFromCallback,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function useAuthToken(): string | null {
  return useAuth().token;
}
