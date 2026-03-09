"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "../../auth/context";

type Citation = { source?: string; snippet?: string };

type ContentBlock = {
  type: string;
  content: string;
  citations?: Citation[];
};

type Lesson = {
  id: string;
  title: string;
  objective: string;
  blocks: ContentBlock[];
};

type Module = {
  id: string;
  title: string;
  objective: string;
  lessons: Lesson[];
};

type CourseSpec = {
  id: string;
  title: string;
  modules: Module[];
};

function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return (
    <div className="mt-2 rounded border-l-2 border-blue-200 bg-blue-50/50 px-2 py-1 text-xs text-stone-600">
      <span className="font-medium text-blue-800">Sources:</span>{" "}
      {citations.map((c, i) => (
        <span key={i}>
          {c.source && <cite>{c.source}</cite>}
          {c.snippet && ` — ${c.snippet.slice(0, 120)}${c.snippet.length > 120 ? "…" : ""}`}
        </span>
      ))}
    </div>
  );
}

function Block({ block }: { block: ContentBlock }) {
  if (block.type === "compliance_note") {
    return (
      <div className="my-4 rounded-lg border-l-4 border-amber-500 bg-amber-50 p-4 text-stone-700">
        <p className="text-sm font-medium text-amber-800">What to ask your RE</p>
        <p className="mt-1">{block.content}</p>
        <CitationList citations={block.citations || []} />
      </div>
    );
  }
  if (block.type === "example") {
    return (
      <div className="my-3 rounded-lg bg-stone-100 p-3 text-stone-700">
        {block.content}
        <CitationList citations={block.citations || []} />
      </div>
    );
  }
  if (block.type === "reflection") {
    return (
      <div>
        <p className="my-3 italic text-stone-600">{block.content}</p>
        <CitationList citations={block.citations || []} />
      </div>
    );
  }
  return (
    <div>
      <p className="my-2 text-stone-700">{block.content}</p>
      <CitationList citations={block.citations || []} />
    </div>
  );
}

export default function CoursePage() {
  const params = useParams();
  const router = useRouter();
  const { token, user, loading: authLoading } = useAuth();
  const id = params.id as string;
  const [course, setCourse] = useState<CourseSpec | null>(null);
  const [progress, setProgress] = useState<{ completed_lesson_ids: string[]; last_lesson_index: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeLesson, setActiveLesson] = useState<{ moduleIndex: number; lessonIndex: number } | null>(null);
  const [feedbackSent, setFeedbackSent] = useState(false);

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
    if (!token) return;
    Promise.all([
      fetch(`/api/v1/course/${id}`, { headers: { Authorization: `Bearer ${token}` } }).then((r) => {
        if (!r.ok) throw new Error(r.statusText);
        return r.json();
      }),
      fetch(`/api/v1/course/${id}/progress`, { headers: { Authorization: `Bearer ${token}` } }).then((r) =>
        r.ok ? r.json() : { completed_lesson_ids: [] as string[], last_lesson_index: 0 }
      ),
    ])
      .then(([spec, prog]) => {
        setCourse(spec);
        setProgress(prog);
        const idx = prog.last_lesson_index ?? 0;
        let count = 0;
        for (let mi = 0; mi < spec.modules.length; mi++) {
          for (let li = 0; li < spec.modules[mi].lessons.length; li++) {
            if (count === idx) {
              setActiveLesson({ moduleIndex: mi, lessonIndex: li });
              return;
            }
            count++;
          }
        }
        if (spec.modules.length > 0) setActiveLesson({ moduleIndex: 0, lessonIndex: 0 });
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id, token]);

  const flatLessonIndex = (moduleIndex: number, lessonIndex: number): number => {
    if (!course) return 0;
    let idx = 0;
    for (let mi = 0; mi < course.modules.length; mi++) {
      for (let li = 0; li < course.modules[mi].lessons.length; li++) {
        if (mi === moduleIndex && li === lessonIndex) return idx;
        idx++;
      }
    }
    return 0;
  };

  const isLessonCompleted = (lessonId: string) => progress?.completed_lesson_ids?.includes(lessonId) ?? false;

  const handleLessonChange = (mi: number, li: number) => {
    const lesson = course?.modules[mi]?.lessons[li];
    if (!lesson || !token) return;
    setFeedbackSent(false);
    const prev = activeLesson;
    setActiveLesson({ moduleIndex: mi, lessonIndex: li });
    const flatIdx = flatLessonIndex(mi, li);
    fetch(`/api/v1/course/${id}/state`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ last_lesson_index: flatIdx }),
    }).catch(() => {});
    if (prev != null) {
      const prevLesson = course?.modules[prev.moduleIndex]?.lessons[prev.lessonIndex];
      if (prevLesson && !isLessonCompleted(prevLesson.id)) {
        fetch(`/api/v1/course/${id}/lesson/${prevLesson.id}/complete`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({ last_lesson_index: flatIdx }),
        })
          .then(() => setProgress((p) => (p ? { ...p, completed_lesson_ids: [...p.completed_lesson_ids, prevLesson.id] } : p)))
          .catch(() => {});
      }
    }
  };

  const sendFeedback = (lessonId: string, value: "up" | "down") => {
    if (!token || feedbackSent) return;
    fetch(`/api/v1/course/${id}/lesson/${lessonId}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ feedback: value }),
    }).then(() => setFeedbackSent(true)).catch(() => {});
  };

  if (authLoading || !token || (user && !user.invite_allowed)) {
    return <p className="text-stone-600">Loading…</p>;
  }
  if (loading) return <p className="text-stone-600">Loading course…</p>;
  if (error) return <p className="text-red-600">{error}</p>;
  if (!course) return null;

  const currentLesson =
    activeLesson != null
      ? course.modules[activeLesson.moduleIndex]?.lessons[activeLesson.lessonIndex]
      : null;

  return (
    <div className="flex gap-8">
      <aside className="w-56 shrink-0 space-y-4">
        <Link href="/" className="text-sm text-amber-700 hover:underline">
          ← Dashboard
        </Link>
        <h2 className="font-semibold text-stone-800">{course.title}</h2>
        <nav className="space-y-2">
          {course.modules.map((mod, mi) => (
            <div key={mod.id}>
              <p className="text-sm font-medium text-stone-600">{mod.title}</p>
              <ul className="mt-1 space-y-0.5 pl-2">
                {mod.lessons.map((les, li) => (
                  <li key={les.id}>
                    <button
                      type="button"
                      onClick={() => handleLessonChange(mi, li)}
                      className={`w-full text-left text-sm hover:underline ${
                        activeLesson?.moduleIndex === mi && activeLesson?.lessonIndex === li
                          ? "font-medium text-amber-700"
                          : "text-stone-600"
                      }`}
                    >
                      {isLessonCompleted(les.id) && <span className="mr-1 text-amber-600">✓ </span>}
                      {les.title}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </aside>
      <article className="min-w-0 flex-1 max-w-2xl">
        {currentLesson ? (
          <>
            <h3 className="text-xl font-semibold text-stone-800">{currentLesson.title}</h3>
            <p className="mt-1 text-stone-600">{currentLesson.objective}</p>
            <div className="mt-6 space-y-2">
              {currentLesson.blocks.map((block, i) => (
                <Block key={i} block={block} />
              ))}
            </div>
            <div className="mt-8 flex items-center gap-2 border-t border-stone-200 pt-4">
              <span className="text-sm text-stone-500">Was this helpful?</span>
              <button
                type="button"
                onClick={() => sendFeedback(currentLesson.id, "up")}
                disabled={feedbackSent}
                className="rounded border border-stone-300 px-2 py-1 text-sm hover:bg-stone-100 disabled:opacity-50"
                aria-label="Yes"
              >
                👍
              </button>
              <button
                type="button"
                onClick={() => sendFeedback(currentLesson.id, "down")}
                disabled={feedbackSent}
                className="rounded border border-stone-300 px-2 py-1 text-sm hover:bg-stone-100 disabled:opacity-50"
                aria-label="No"
              >
                👎
              </button>
              {feedbackSent && <span className="text-sm text-stone-500">Thanks for your feedback.</span>}
            </div>
          </>
        ) : (
          <p className="text-stone-500">Select a lesson.</p>
        )}
      </article>
    </div>
  );
}
