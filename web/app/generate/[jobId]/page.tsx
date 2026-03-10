"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "../../auth/context";

const STREAM_TIMEOUT_MS = 150000; // 2.5 minutes

function friendlyErrorMessage(raw: string): string {
  const s = raw.trim();
  if (s.includes("Job not found") || s.includes("expired")) {
    return "This link has expired or the job was not found.";
  }
  if (s.includes("Timeout") || s.toLowerCase().includes("timeout")) {
    return "The request took too long.";
  }
  if (s.includes("Connection lost") || s.includes("lost connection")) {
    return "We lost connection. Please check your network and try again.";
  }
  if (
    s.includes("Generation failed") ||
    s.includes("QA did not pass") ||
    s.includes("did not pass")
  ) {
    return "We couldn't complete your course this time. Try again with slightly different answers.";
  }
  return "Something went wrong. Please try again.";
}

export default function GeneratePage() {
  const params = useParams();
  const router = useRouter();
  const { token, user, loading: authLoading } = useAuth();
  const jobId = params.jobId as string;
  const [message, setMessage] = useState("Connecting…");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const finishedRef = useRef(false);

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
    finishedRef.current = false;
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
    const url = `${apiBase}/v1/generate/${jobId}/stream?token=${encodeURIComponent(token)}`;
    const eventSource = new EventSource(url);

    const setErrorFriendly = (raw: string) => {
      if (finishedRef.current) return;
      finishedRef.current = true;
      setError(friendlyErrorMessage(raw));
      eventSource.close();
    };

    const timeoutId = window.setTimeout(() => {
      if (finishedRef.current) return;
      finishedRef.current = true;
      setError(
        "This is taking longer than usual. You can try again or start over."
      );
      eventSource.close();
    }, STREAM_TIMEOUT_MS);

    eventSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.error) {
          setErrorFriendly(data.error);
          return;
        }
        if (data.message) setMessage(data.message);
        if (typeof data.progress === "number") setProgress(data.progress);
        if (data.done && data.course_id) {
          finishedRef.current = true;
          eventSource.close();
          const courseId = String(data.course_id);
          if (courseId && courseId !== "undefined") {
            router.push(`/course/${courseId}`);
          }
        } else if (data.done && data.error) {
          setErrorFriendly(data.error);
        }
      } catch {
        setErrorFriendly("Something went wrong.");
      }
    };

    eventSource.onerror = () => {
      setErrorFriendly(
        "We lost connection. Please check your network and try again."
      );
    };

    return () => {
      window.clearTimeout(timeoutId);
      eventSource.close();
    };
  }, [jobId, token, router]);

  if (authLoading || !token || (user && !user.invite_allowed)) {
    return <p className="text-stone-600">Loading…</p>;
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <h1 className="text-xl font-semibold text-stone-800">Building your course</h1>
      {error ? (
        <div
          className="rounded-lg border border-red-200 bg-red-50 p-4 space-y-4"
          role="alert"
        >
          <h2 className="font-medium text-red-800">We couldn&apos;t build your course</h2>
          <p className="text-red-700 text-sm">{error}</p>
          <Link
            href="/intake"
            className="inline-block rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700"
          >
            Start over
          </Link>
        </div>
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
