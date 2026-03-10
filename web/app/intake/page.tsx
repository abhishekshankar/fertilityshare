"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../auth/context";

function intakeErrorMessage(status: number, detail: unknown): string {
  if (status === 401) return "Please sign in again.";
  if (status === 403) {
    if (typeof detail === "string") return detail;
    return "You don't have access to create a course.";
  }
  if (status === 422) {
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0];
      const msg = first?.msg ?? first?.message ?? JSON.stringify(first);
      return typeof msg === "string" ? msg : JSON.stringify(msg);
    }
    return "Please check your answers and try again.";
  }
  if (status >= 500) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  return "Something went wrong. Please try again.";
}

const JOURNEY_OPTIONS = [
  "Newly diagnosed",
  "Preparing for first IUI",
  "Preparing for first IVF",
  "After failed cycle / veteran",
  "Considering egg freezing",
  "Partner supporting someone",
  "I don't know yet",
];

const DIAGNOSIS_OPTIONS = [
  "PCOS",
  "Low AMH",
  "MFI (male factor)",
  "Unexplained",
  "I don't know yet",
];

const LEVEL_OPTIONS = ["beginner", "intermediate", "advanced"] as const;

export default function IntakePage() {
  const router = useRouter();
  const { token, user, loading: authLoading } = useAuth();
  const [step, setStep] = useState(1);
  const [journeyStage, setJourneyStage] = useState("");
  const [diagnosis, setDiagnosis] = useState("");
  const [confusion, setConfusion] = useState("");
  const [level, setLevel] = useState<"beginner" | "intermediate" | "advanced">("beginner");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (authLoading) return;
    if (!token) {
      router.replace("/login");
      return;
    }
    if (user && !user.invite_allowed) {
      router.replace("/waitlist");
    }
  }, [authLoading, token, user, router]);

  const handleSubmit = async () => {
    if (!token) return;
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/v1/generate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          journey_stage: journeyStage,
          diagnosis: diagnosis || null,
          confusion: confusion.trim() || "I want to understand my options.",
          level,
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        let detail: unknown = text;
        try {
          const j = JSON.parse(text);
          detail = j.detail ?? text;
        } catch {
          // leave detail as text
        }
        const message = intakeErrorMessage(res.status, detail);
        setError(message);
        setLoading(false);
        return;
      }
      const data = await res.json();
      const jobId = data.job_id != null ? String(data.job_id) : null;
      if (jobId && jobId !== "undefined") {
        router.push(`/generate/${jobId}`);
      } else {
        setError("Something went wrong. Please try again.");
      }
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Something went wrong. Please try again."
      );
    } finally {
      setLoading(false);
    }
  };

  if (authLoading || !token || (user && !user.invite_allowed)) {
    return <p className="text-stone-600">Loading…</p>;
  }

  return (
    <div className="mx-auto max-w-lg space-y-8">
      <h1 className="text-2xl font-semibold text-stone-800">Create your course</h1>
      <div className="flex gap-1">
        {[1, 2, 3, 4].map((s) => (
          <div
            key={s}
            className={`h-1 flex-1 rounded ${
              s <= step ? "bg-amber-600" : "bg-stone-200"
            }`}
          />
        ))}
      </div>

      {error && (
        <div
          className="rounded-lg border border-red-200 bg-red-50 p-4"
          role="alert"
        >
          <p className="text-red-700 text-sm">{error}</p>
          {error === "Please sign in again." && (
            <Link
              href="/login"
              className="mt-2 inline-block text-sm font-medium text-amber-700 underline hover:text-amber-800"
            >
              Sign in again
            </Link>
          )}
        </div>
      )}

      {step === 1 && (
        <div className="space-y-4">
          <label className="block font-medium text-stone-700">Where are you in your journey?</label>
          <div className="space-y-2">
            {JOURNEY_OPTIONS.map((opt) => (
              <label key={opt} className="flex cursor-pointer items-center gap-2">
                <input
                  type="radio"
                  name="journey"
                  value={opt}
                  checked={journeyStage === opt}
                  onChange={() => setJourneyStage(opt)}
                  className="h-4 w-4 text-amber-600"
                />
                <span>{opt}</span>
              </label>
            ))}
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          <label className="block font-medium text-stone-700">Diagnosis (if any)</label>
          <div className="space-y-2">
            {DIAGNOSIS_OPTIONS.map((opt) => (
              <label key={opt} className="flex cursor-pointer items-center gap-2">
                <input
                  type="radio"
                  name="diagnosis"
                  value={opt}
                  checked={diagnosis === opt}
                  onChange={() => setDiagnosis(opt)}
                  className="h-4 w-4 text-amber-600"
                />
                <span>{opt}</span>
              </label>
            ))}
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-4">
          <label className="block font-medium text-stone-700">
            What’s your biggest question or confusion right now?
          </label>
          <textarea
            value={confusion}
            onChange={(e) => setConfusion(e.target.value)}
            placeholder="e.g. I don't understand stim protocols"
            className="w-full rounded-lg border border-stone-300 p-3 text-stone-800 placeholder:text-stone-400"
            rows={4}
          />
        </div>
      )}

      {step === 4 && (
        <div className="space-y-4">
          <label className="block font-medium text-stone-700">Knowledge level</label>
          <div className="space-y-2">
            {LEVEL_OPTIONS.map((opt) => (
              <label key={opt} className="flex cursor-pointer items-center gap-2">
                <input
                  type="radio"
                  name="level"
                  value={opt}
                  checked={level === opt}
                  onChange={() => setLevel(opt)}
                  className="h-4 w-4 text-amber-600"
                />
                <span className="capitalize">{opt}</span>
              </label>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-3">
        {step > 1 && (
          <button
            type="button"
            onClick={() => setStep((s) => s - 1)}
            className="rounded-lg border border-stone-300 px-4 py-2 text-stone-700 hover:bg-stone-100"
          >
            Back
          </button>
        )}
        {step < 4 ? (
          <button
            type="button"
            onClick={() => setStep((s) => s + 1)}
            disabled={
              (step === 1 && !journeyStage) ||
              (step === 2 && !diagnosis)
            }
            className="rounded-lg bg-amber-600 px-4 py-2 font-medium text-white hover:bg-amber-700 disabled:opacity-50"
          >
            Next
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSubmit}
            disabled={loading}
            className="rounded-lg bg-amber-600 px-4 py-2 font-medium text-white hover:bg-amber-700 disabled:opacity-50"
          >
            {loading ? "Starting…" : "Generate my course"}
          </button>
        )}
      </div>
    </div>
  );
}
