"use client";

import Link from "next/link";
import { useAuth } from "./context";

export function AuthNavClient() {
  const { token, user, loading, signOut } = useAuth();
  if (loading) return <span className="text-stone-400">…</span>;
  if (!token) {
    return (
      <Link href="/login" className="text-amber-700 hover:underline">
        Sign in
      </Link>
    );
  }
  return (
    <>
      <span className="text-stone-600">{user?.email}</span>
      <button
        type="button"
        onClick={() => signOut()}
        className="text-stone-500 hover:text-stone-700"
      >
        Sign out
      </button>
    </>
  );
}
