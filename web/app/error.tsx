"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("App error:", error);
  }, [error]);

  return (
    <div className="mx-auto max-w-md space-y-4 rounded-lg border border-red-200 bg-red-50 p-6 text-red-900">
      <h2 className="text-lg font-semibold">Something went wrong</h2>
      <p className="text-sm font-mono">{error.message}</p>
      <button
        type="button"
        onClick={() => reset()}
        className="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
      >
        Try again
      </button>
    </div>
  );
}
