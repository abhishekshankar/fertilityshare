"use client";

import Link from "next/link";
import { useAuth } from "../auth/context";

export default function WaitlistPage() {
  const { user, loading, token } = useAuth();

  if (loading) return <p className="text-stone-600">Loading…</p>;
  if (!token) {
    return (
      <div className="mx-auto max-w-md text-center">
        <p className="text-stone-600">Please sign in first.</p>
        <Link href="/login" className="mt-4 inline-block text-amber-700 hover:underline">
          Go to sign in
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md space-y-4 text-center">
      <h1 className="text-2xl font-semibold text-stone-800">You&apos;re on the list</h1>
      <p className="text-stone-600">
        Thanks for signing up{user?.email ? `, ${user.email}` : ""}. We&apos;re in invite-only
        beta. You&apos;ll get access soon.
      </p>
      <p className="text-sm text-stone-500">
        <Link href="/" className="text-amber-700 hover:underline">
          Back to home
        </Link>
      </p>
    </div>
  );
}
