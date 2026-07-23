/**
 * Home — BOB system status page (M0's "everything is wired" proof).
 *
 * SERVER COMPONENT (no "use client"): this function runs on the Next.js
 * server; the browser receives finished HTML. The fetch below is therefore
 * server-to-server — CORS never enters the picture here. (Browser-side
 * calls arrive with the dashboard forms in M1; CORS is already configured
 * for them on the backend.)
 *
 * This page becomes the marketing/landing page later; today its job is to
 * make the M0 wire-up VISIBLE: frontend → backend → database, one glance.
 */

import { fetchHealth } from "@/lib/api";

/** One row of the checks report. Green dot = ok, red = anything else. */
function CheckRow({ name, value }: { name: string; value: string }) {
  const ok = value === "ok";
  return (
    <li className="flex items-center justify-between rounded-lg border border-zinc-200 px-4 py-3 dark:border-zinc-800">
      <span className="font-mono text-sm">{name}</span>
      <span className="flex items-center gap-2 text-sm">
        <span
          className={`inline-block h-2.5 w-2.5 rounded-full ${
            ok ? "bg-green-500" : "bg-red-500"
          }`}
        />
        {value}
      </span>
    </li>
  );
}

export default async function Home() {
  // null = backend unreachable. That state is DESIGNED, not accidental:
  // the page still renders, tells the truth, and stays calm.
  const health = await fetchHealth();

  return (
    <div className="flex flex-1 items-center justify-center bg-zinc-50 font-sans dark:bg-black">
      <main className="w-full max-w-md px-6">
        <h1 className="text-2xl font-bold tracking-tight">
          BOB <span className="text-zinc-400">for Commerce</span>
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          Post once. Sell everywhere.
        </p>

        <div className="mt-8">
          {health ? (
            <>
              <p className="mb-3 text-sm text-zinc-500">
                {health.service} · {health.env} ·{" "}
                <span
                  className={
                    health.status === "ok" ? "text-green-600" : "text-amber-600"
                  }
                >
                  {health.status}
                </span>
              </p>
              <ul className="space-y-2">
                {Object.entries(health.checks).map(([name, value]) => (
                  <CheckRow key={name} name={name} value={value} />
                ))}
              </ul>
            </>
          ) : (
            /* Backend down: say so plainly. A tester reading this knows
               exactly what to report — "backend unreachable", not "site broken". */
            <ul className="space-y-2">
              <CheckRow name="backend" value="unreachable" />
            </ul>
          )}
        </div>
      </main>
    </div>
  );
}
