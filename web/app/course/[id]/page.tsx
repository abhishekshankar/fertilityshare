"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, useCallback } from "react";
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
  key_takeaways?: string[];
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
  generation_status?: string;
  job_id?: string;
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

function LessonSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-6 w-2/3 rounded bg-stone-200" />
      <div className="h-4 w-full rounded bg-stone-200" />
      <div className="space-y-3 pt-4">
        <div className="h-4 w-full rounded bg-stone-100" />
        <div className="h-4 w-full rounded bg-stone-100" />
        <div className="h-4 w-5/6 rounded bg-stone-100" />
        <div className="h-20 w-full rounded bg-stone-100" />
        <div className="h-4 w-full rounded bg-stone-100" />
        <div className="h-4 w-3/4 rounded bg-stone-100" />
      </div>
    </div>
  );
}

function GenerationBanner({ message, completedCount, totalCount }: { message: string; completedCount: number; totalCount: number }) {
  const pct = totalCount > 0 ? Math.round((100 * completedCount) / totalCount) : 0;
  return (
    <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50/80 p-4">
      <div className="flex items-center gap-2">
        <svg className="h-5 w-5 animate-spin text-amber-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
        <p className="text-sm font-medium text-amber-800">{message}</p>
      </div>
      {totalCount > 0 && (
        <div className="mt-2">
          <div className="flex justify-between text-xs text-amber-700">
            <span>{completedCount} of {totalCount} lessons ready</span>
            <span>{pct}%</span>
          </div>
          <div className="mt-1 h-1.5 w-full rounded-full bg-amber-200">
            <div
              className="h-1.5 rounded-full bg-amber-600 transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

const isLessonLoaded = (lesson: Lesson) => lesson.blocks && lesson.blocks.length > 0;

export default function CoursePage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { token, user, loading: authLoading } = useAuth();
  const id = params.id as string;
  const jobIdFromUrl = searchParams.get("job_id");
  const [course, setCourse] = useState<CourseSpec | null>(null);
  const [progress, setProgress] = useState<{ completed_lesson_ids: string[]; last_lesson_index: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeLesson, setActiveLesson] = useState<{ moduleIndex: number; lessonIndex: number } | null>(null);
  const [feedbackSent, setFeedbackSent] = useState(false);
  const articleRef = useRef<HTMLElement>(null);
  const hasScrolledToResumeRef = useRef(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationMessage, setGenerationMessage] = useState("Building your course...");
  const [generatedLessonCount, setGeneratedLessonCount] = useState(0);
  const [totalLessonCount, setTotalLessonCount] = useState(0);
  const sseRef = useRef<EventSource | null>(null);
  const autoSelectedRef = useRef(false);

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
    if (!id || id === "undefined") {
      router.replace("/");
      return;
    }
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
        const genStatus = spec.generation_status || "complete";
        if (genStatus === "generating") {
          setIsGenerating(true);
          const total = (spec.modules || []).reduce((acc: number, m: Module) => acc + (m.lessons?.length || 0), 0);
          const loaded = (spec.modules || []).reduce(
            (acc: number, m: Module) => acc + (m.lessons || []).filter((l: Lesson) => l.blocks && l.blocks.length > 0).length,
            0
          );
          setTotalLessonCount(total);
          setGeneratedLessonCount(loaded);
        } else {
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
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id, token, router]);

  const connectToSSE = useCallback(() => {
    if (!token) return;
    const jobId = jobIdFromUrl || course?.job_id;
    if (!jobId) return;

    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
    const url = `${apiBase}/v1/generate/${jobId}/stream?token=${encodeURIComponent(token)}`;
    const eventSource = new EventSource(url);
    sseRef.current = eventSource;

    eventSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);

        if (data.event === "outline_ready" && data.modules) {
          const total = data.modules.reduce((acc: number, m: { lessons: unknown[] }) => acc + m.lessons.length, 0);
          setTotalLessonCount(total);
          setCourse((prev) => {
            const newModules: Module[] = data.modules.map((mod: { id: string; title: string; objective?: string; lessons: { id: string; title: string; objective?: string }[] }) => ({
              id: mod.id,
              title: mod.title,
              objective: mod.objective || "",
              lessons: mod.lessons.map((les) => ({
                id: les.id,
                title: les.title,
                objective: les.objective || "",
                blocks: [],
                key_takeaways: [],
              })),
            }));
            return prev
              ? { ...prev, modules: newModules, title: newModules.length === 1 ? newModules[0].title : prev.title }
              : { id: "", title: newModules.length === 1 ? newModules[0].title : "Your course", modules: newModules };
          });
          setGenerationMessage("Writing lessons...");
        }

        if (data.event === "lesson_ready" && data.lesson) {
          const modIdx = data.module_index;
          const lesIdx = data.lesson_index;
          setCourse((prev) => {
            if (!prev) return prev;
            const newModules = prev.modules.map((mod, mi) => {
              if (mi !== modIdx) return mod;
              const newLessons = mod.lessons.map((les, li) => (li === lesIdx ? data.lesson : les));
              return { ...mod, lessons: newLessons };
            });
            return { ...prev, modules: newModules };
          });
          setGeneratedLessonCount((c) => c + 1);
          if (!autoSelectedRef.current) {
            autoSelectedRef.current = true;
            setActiveLesson({ moduleIndex: modIdx, lessonIndex: lesIdx });
          }
        }

        if (data.event === "generation_complete") {
          setIsGenerating(false);
          setGenerationMessage("");
          eventSource.close();
          sseRef.current = null;
        }

        if (data.event === "intent" || data.event === "research") {
          if (data.message) setGenerationMessage(data.message);
        }

        if (data.done) {
          setIsGenerating(false);
          eventSource.close();
          sseRef.current = null;
        }

        if (data.error) {
          setIsGenerating(false);
          eventSource.close();
          sseRef.current = null;
        }
      } catch {
        // ignore parse errors
      }
    };

    eventSource.onerror = () => {
      setIsGenerating(false);
      eventSource.close();
      sseRef.current = null;
    };
  }, [token, jobIdFromUrl, course?.job_id]);

  useEffect(() => {
    if (!isGenerating || sseRef.current) return;
    connectToSSE();
    return () => {
      sseRef.current?.close();
      sseRef.current = null;
    };
  }, [isGenerating, connectToSSE]);

  useEffect(() => {
    if (!activeLesson || !course || hasScrolledToResumeRef.current) return;
    hasScrolledToResumeRef.current = true;
    const timer = requestAnimationFrame(() => {
      articleRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return () => cancelAnimationFrame(timer);
  }, [activeLesson, course]);

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
    if (!isLessonLoaded(lesson) && isGenerating) return;
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
      if (prevLesson && isLessonLoaded(prevLesson) && !isLessonCompleted(prevLesson.id)) {
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

  const hasModules = course.modules && course.modules.length > 0;
  const totalLessons = course.modules.reduce((acc, m) => acc + m.lessons.length, 0);
  const completedCount = progress?.completed_lesson_ids?.length ?? 0;
  const completionPct = totalLessons ? Math.round((100 * completedCount) / totalLessons) : 0;

  const currentLesson =
    activeLesson != null
      ? course.modules[activeLesson.moduleIndex]?.lessons[activeLesson.lessonIndex]
      : null;

  if (!hasModules && isGenerating) {
    return (
      <div className="mx-auto max-w-lg space-y-6">
        <h1 className="text-xl font-semibold text-stone-800">Building your course</h1>
        <GenerationBanner message={generationMessage} completedCount={0} totalCount={0} />
        <div className="animate-pulse space-y-4">
          <div className="h-5 w-1/2 rounded bg-stone-200" />
          <div className="h-4 w-3/4 rounded bg-stone-100" />
          <div className="h-4 w-2/3 rounded bg-stone-100" />
          <div className="h-4 w-3/4 rounded bg-stone-100" />
        </div>
      </div>
    );
  }

  const genStatus = course.generation_status || "complete";
  const isPartial = genStatus === "partial";

  return (
    <div className="flex gap-8">
      <aside className="w-56 shrink-0 space-y-4">
        <Link href="/" className="text-sm text-amber-700 hover:underline">
          ← Dashboard
        </Link>
        <h2 className="font-semibold text-stone-800">{course.title}</h2>
        {!isGenerating && (
          <div className="space-y-1">
            <p className="text-sm text-stone-600">
              {completedCount} of {totalLessons} lessons complete
            </p>
            <div className="h-1.5 w-full rounded-full bg-stone-200">
              <div
                className="h-1.5 rounded-full bg-amber-600 transition-all duration-300"
                style={{ width: `${Math.min(100, Math.max(0, completionPct))}%` }}
              />
            </div>
          </div>
        )}
        {isPartial && (
          <div className="rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
            Generation incomplete — {generatedLessonCount} of {totalLessonCount || totalLessons} lessons available.
          </div>
        )}
        <nav className="space-y-2">
          {course.modules.map((mod, mi) => (
            <div key={mod.id}>
              <p className="text-sm font-medium text-stone-600">{mod.title}</p>
              <ul className="mt-1 space-y-0.5 pl-2">
                {mod.lessons.map((les, li) => {
                  const loaded = isLessonLoaded(les);
                  const isActive = activeLesson?.moduleIndex === mi && activeLesson?.lessonIndex === li;
                  return (
                    <li key={les.id}>
                      <button
                        type="button"
                        onClick={() => handleLessonChange(mi, li)}
                        disabled={!loaded && isGenerating}
                        className={`w-full text-left text-sm hover:underline ${
                          isActive ? "font-medium text-amber-700" : loaded ? "text-stone-600" : "text-stone-400"
                        } ${!loaded && isGenerating ? "cursor-wait" : ""}`}
                      >
                        {isLessonCompleted(les.id) && <span className="mr-1 text-amber-600">✓ </span>}
                        {!loaded && isGenerating && <span className="mr-1 inline-block h-2 w-2 animate-pulse rounded-full bg-amber-400" />}
                        {les.title}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>
      </aside>
      <article ref={articleRef} className="min-w-0 flex-1 max-w-2xl">
        {isGenerating && (
          <GenerationBanner
            message={generationMessage}
            completedCount={generatedLessonCount}
            totalCount={totalLessonCount}
          />
        )}
        {currentLesson && isLessonLoaded(currentLesson) ? (
          <>
            <h3 className="text-xl font-semibold text-stone-800">{currentLesson.title}</h3>
            <p className="mt-1 text-stone-600">{currentLesson.objective}</p>
            {currentLesson.key_takeaways && currentLesson.key_takeaways.length > 0 && (
              <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/80 p-4 shadow-sm">
                <p className="mb-2 text-sm font-semibold uppercase tracking-wide text-amber-800">
                  Key takeaways
                </p>
                <ul className="list-inside list-disc space-y-1 text-stone-700">
                  {currentLesson.key_takeaways.map((takeaway, i) => (
                    <li key={i}>{takeaway}</li>
                  ))}
                </ul>
              </div>
            )}
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
        ) : currentLesson && isGenerating ? (
          <div>
            <h3 className="text-xl font-semibold text-stone-800">{currentLesson.title}</h3>
            <p className="mt-1 text-stone-600">{currentLesson.objective}</p>
            <div className="mt-6">
              <LessonSkeleton />
            </div>
          </div>
        ) : !isGenerating && !currentLesson && hasModules ? (
          <p className="text-stone-500">Select a lesson.</p>
        ) : null}
      </article>
    </div>
  );
}
