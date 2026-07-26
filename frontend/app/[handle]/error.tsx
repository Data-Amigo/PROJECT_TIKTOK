"use client";

/**
 * Error boundary for sokolink/<handle>. Catches the "backend is down / fetch
 * failed" throw from fetchPublicPage (NOT a 404 — that goes to not-found.tsx).
 * A customer sees "try again", never a stack trace or a false "shop doesn't
 * exist". Must be a client component — Next requires error boundaries to be.
 */

export default function ShopError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 px-4 dark:bg-black">
      <div className="text-center">
        <p className="text-4xl">😕</p>
        <h1 className="mt-4 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          Couldn&apos;t load this shop
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          Something went wrong on our side. Please try again in a moment.
        </p>
        <button
          onClick={reset}
          className="mt-6 rounded-lg bg-black px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-white dark:text-black"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
