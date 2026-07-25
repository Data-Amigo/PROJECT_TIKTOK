/**
 * 404 for bob.link/<handle> when no such shop exists. A real not-found page
 * (Next serves it with HTTP 404), not a broken-looking empty shop — a customer
 * who mistypes a link gets a clear, calm answer.
 */

import Link from "next/link";

export default function ShopNotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 px-4 dark:bg-black">
      <div className="text-center">
        <p className="text-5xl font-bold text-zinc-300 dark:text-zinc-700">404</p>
        <h1 className="mt-4 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          Shop not found
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          This link doesn&apos;t point to a shop. Check the address and try again.
        </p>
        <Link
          href="/"
          className="mt-6 inline-block rounded-lg bg-black px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-white dark:text-black"
        >
          Go home
        </Link>
      </div>
    </div>
  );
}
