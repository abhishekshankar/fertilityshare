"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "./auth/context";

type CourseItem = { id: string; title: string; created_at: string | null; completion_pct: number };

export default function HomePage() {
  const { token, user, loading: authLoading } = useAuth();
  const [courses, setCourses] = useState<CourseItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    fetch("/api/v1/courses", { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : []))
      .then(setCourses)
      .catch(() => setCourses([]))
      .finally(() => setLoading(false));
  }, [token]);

  if (authLoading) return <p className="text-stone-600">Loading…</p>;
  if (!token) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold text-stone-800">
          Your fertility learning course
        </h1>
        <p className="text-stone-600">
          Answer a few questions and we’ll build a personalized, medically-grounded
          course for where you are in your journey.
        </p>
        <Link
          href="/login"
          className="inline-block rounded-lg bg-amber-600 px-4 py-2 font-medium text-white hover:bg-amber-700"
        >
          Sign in to start
        </Link>
      </div>
    );
  }
  if (user && !user.invite_allowed) {
    return (
      <p className="text-stone-600">
        You’re on the list. <Link href="/waitlist" className="text-amber-700 hover:underline">View status</Link>
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-stone-800">Your courses</h1>
      {loading ? (
        <p className="text-stone-600">Loading…</p>
      ) : courses.length === 0 ? (
        <p className="text-stone-600">No courses yet. Create your first one.</p>
      ) : (
        <ul className="space-y-3">
          {courses.map((c) => (
            <li key={c.id}>
              <Link
                href={`/course/${c.id}`}
                className="block rounded-lg border border-stone-200 bg-white p-4 shadow-sm transition hover:border-amber-300"
              >
                <span className="font-medium text-stone-800">{c.title}</span>
                <span className="ml-2 text-sm text-stone-500">{c.completion_pct}% complete</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <Link
        href="/intake"
        className="inline-block rounded-lg bg-amber-600 px-4 py-2 font-medium text-white hover:bg-amber-700"
      >
        {courses.length === 0 ? "Create your course" : "Create another course"}
      </Link>
    </div>
  );
}
