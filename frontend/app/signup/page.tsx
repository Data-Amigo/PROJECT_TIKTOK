"use client";

/**
 * Seller signup. Creates an account, logs in (token stored), → dashboard.
 * A client component: it holds form state, calls the backend, and redirects.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { signup } from "@/lib/auth";

export default function SignupPage() {
  const router = useRouter();
  const [form, setForm] = useState({ name: "", email: "", phone: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signup(form);
      router.replace("/dashboard"); // replace → back button won't return to signup
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 px-4 dark:bg-black">
      <div className="w-full max-w-sm">
        <h1 className="text-2xl font-bold tracking-tight">
          Create your <span className="text-zinc-400">BOB</span> shop
        </h1>
        <p className="mt-1 text-sm text-zinc-500">Sell your TikTok drops. Pay with M-Pesa.</p>

        <form onSubmit={submit} className="mt-8 flex flex-col gap-3">
          <Field label="Your name" value={form.name} onChange={set("name")} placeholder="Mama Wanjiku" autoComplete="name" />
          <Field label="Email" type="email" value={form.email} onChange={set("email")} placeholder="you@example.com" autoComplete="email" />
          <Field label="Phone (M-Pesa)" value={form.phone} onChange={set("phone")} placeholder="0712345678" autoComplete="tel" />
          <Field label="Password" type="password" value={form.password} onChange={set("password")} placeholder="at least 8 characters" autoComplete="new-password" />

          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="mt-2 rounded-lg bg-black px-4 py-2.5 text-sm font-semibold text-white hover:bg-zinc-800 disabled:opacity-40 dark:bg-white dark:text-black"
          >
            {busy ? "Creating…" : "Create account"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-zinc-500">
          Already have a shop?{" "}
          <Link href="/login" className="font-medium text-zinc-900 underline dark:text-zinc-100">
            Log in
          </Link>
        </p>
      </div>
    </div>
  );
}

function Field({
  label,
  ...props
}: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="text-xs font-medium text-zinc-500">
      {label}
      <input
        {...props}
        required
        className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
      />
    </label>
  );
}
