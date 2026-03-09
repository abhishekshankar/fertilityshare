"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "../../auth/context";

export default function GeneratePage() {
  const params = useParams();
  const router = useRouter();
  const { token, user, loading: authLoading } = useAuth();
  const jobId = params.jobId as string;
  const [message, setMessage] = useState("Connecting…");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    if (authLoading) return;
    if (!token) {
      router.replace("/login");
      return;
    }
    if (user && !user.invite_allowed) {
      router.replace("/waitlist");
      return;
    }
  }, [authLoading, token, user, router]);

  useEffect(() => {
    if (!jobId || !token) return;
    // Connect directly to the backend for SSE — Next.js rewrite proxy buffers responses
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
    const url = `${apiBase}/v1/generate/${jobId}/stream?token=${encodeURIComponent(token)}`;
    const eventSource = new EventSource(url);

    eventSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.error) {
          setError(data.error);
          eventSource.close();
          return;
        }
        if (data.message) setMessage(data.message);
        if (typeof data.progress === "number") setProgress(data.progress);
        if (data.done && data.course_id) {
          eventSource.close();
          router.push(`/course/${data.course_id}`);
        } else if (data.done && data.error) {
          setError(data.error);
          eventSource.close();
        }
      } catch (_) {}
    };

    eventSource.onerror = () => {
      setError("Connection lost. Check that the API is running and you're signed in.");
      eventSource.close();
    };

    return () => eventSource.close();
  }, [jobId, token, router]);

  if (authLoading || !token || (user && !user.invite_allowed)) {
    return <p className="text-stone-600">Loading…</p>;
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <h1 className="text-xl font-semibold text-stone-800">Building your course</h1>
      {error ? (
        <p className="text-red-600">{error}</p>
      ) : (
        <>
          <p className="text-stone-600">{message}</p>
          <div className="h-2 w-full overflow-hidden rounded-full bg-stone-200">
            <div
              className="h-full bg-amber-600 transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </>
      )}
    </div>
  );
}
