"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "../context";

function AuthCallbackContent() {
  const searchParams = useSearchParams();
  const { setTokenFromCallback, user, loading } = useAuth();
  const [done, setDone] = useState(false);

  useEffect(() => {
    const token = searchParams.get("token");
    // #region agent log
    fetch('http://127.0.0.1:7783/ingest/cc850ea7-3322-438b-a856-c76e4d0f2158',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'41ee7a'},body:JSON.stringify({sessionId:'41ee7a',location:'callback/page.tsx:effect1',message:'callback_effect1',data:{hasToken:!!token,tokenLen:token?.length??0,done},timestamp:Date.now(),hypothesisId:'H2'})}).catch(()=>{});
    // #endregion
    if (token && !done) {
      setTokenFromCallback(token);
      setDone(true);
    }
  }, [searchParams, setTokenFromCallback, done]);

  useEffect(() => {
    const token = searchParams.get("token");
    // When we have a token in the URL and we've set it, go to home immediately.
    // The app will finish loading the user there; we avoid redirecting to /login
    // while fetchUser is still in progress or due to a transient failure.
    if (done && token) {
      window.location.href = "/";
      return;
    }
    if (!loading && done && !token) {
      if (!user) {
        window.location.href = "/login?error=google_signin_failed";
        return;
      }
      if (user.invite_allowed) {
        window.location.href = "/";
      } else {
        window.location.href = "/waitlist";
      }
    }
  }, [loading, user, done, searchParams, setTokenFromCallback]);

  return (
    <div className="flex min-h-[40vh] items-center justify-center text-stone-600">
      Signing you in…
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[40vh] items-center justify-center text-stone-600">
          Signing you in…
        </div>
      }
    >
      <AuthCallbackContent />
    </Suspense>
  );
}
