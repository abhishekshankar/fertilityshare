"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, useEffect } from "react";
import { useAuth } from "../auth/context";

const ERROR_MESSAGES: Record<string, string> = {
  access_denied: "Google sign-in was cancelled or denied.",
  token_exchange_failed: "Google sign-in failed (token exchange). Please try again.",
  no_token: "Google sign-in failed (no token). Please try again.",
  userinfo_failed: "Google sign-in failed (could not load profile). Please try again.",
  missing_profile: "Google sign-in failed (missing email or profile). Please try again.",
  google_signin_failed: "Sign-in with Google did not complete. Please try again.",
};

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { signIn, user, loading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const err = searchParams.get("error");
    if (err && ERROR_MESSAGES[err]) setError(ERROR_MESSAGES[err]);
  }, [searchParams]);

  const apiBase = "/api";

  if (loading) return <p className="text-stone-600">Loading…</p>;
  if (user?.invite_allowed) {
    router.replace("/");
    return null;
  }
  if (user && !user.invite_allowed) {
    router.replace("/waitlist");
    return null;
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const res = await fetch(`${apiBase}/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Login failed");
      }
      const data = await res.json();
      signIn(data.access_token);
      router.push("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const res = await fetch(`${apiBase}/v1/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Registration failed");
      }
      const data = await res.json();
      signIn(data.access_token);
      router.push("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Registration failed");
    } finally {
      setSubmitting(false);
    }
  };

  const googleAuthUrl = `${apiBase}/v1/auth/google`;

  return (
    <div className="mx-auto max-w-sm space-y-6">
      <h1 className="text-2xl font-semibold text-stone-800">Sign in</h1>

      <a
        href={googleAuthUrl}
        className="flex w-full items-center justify-center gap-2 rounded-lg border border-stone-300 bg-white px-4 py-2.5 text-stone-700 hover:bg-stone-50"
      >
        Sign in with Google
      </a>

      <form className="space-y-4" onSubmit={handleLogin}>
        <div>
          <label className="block text-sm font-medium text-stone-700">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-stone-800"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-stone-700">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-stone-800"
            required
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex gap-2">
          <button
            type="submit"
            disabled={submitting}
            className="flex-1 rounded-lg bg-amber-600 px-4 py-2 font-medium text-white hover:bg-amber-700 disabled:opacity-50"
          >
            Sign in
          </button>
          <button
            type="button"
            onClick={handleRegister}
            disabled={submitting}
            className="flex-1 rounded-lg border border-stone-300 px-4 py-2 text-stone-700 hover:bg-stone-100 disabled:opacity-50"
          >
            Register
          </button>
        </div>
      </form>

      <p className="text-center text-sm text-stone-500">
        <Link href="/" className="text-amber-700 hover:underline">
          Back to home
        </Link>
      </p>
    </div>
  );
}
