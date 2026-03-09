"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "../context";

export default function AuthCallbackPage() {
  const searchParams = useSearchParams();
  const { setTokenFromCallback, user, loading } = useAuth();
  const [done, setDone] = useState(false);

  useEffect(() => {
    const token = searchParams.get("token");
    if (token && !done) {
      setTokenFromCallback(token);
      setDone(true);
    }
  }, [searchParams, setTokenFromCallback, done]);

  useEffect(() => {
    if (!loading && done) {
      if (!user) {
        window.location.href = "/login";
        return;
      }
      if (user.invite_allowed) {
        window.location.href = "/";
      } else {
        window.location.href = "/waitlist";
      }
    }
  }, [loading, user, done]);

  return (
    <div className="flex min-h-[40vh] items-center justify-center text-stone-600">
      Signing you in…
    </div>
  );
}
