"use client";

/**
 * OrderButton — the buyer's call to action on an available product.
 *
 * Checkout (M-Pesa STK push) is M2, not built yet. Rather than fake it or hide
 * it, this button is honest: tapping it reveals that checkout is launching
 * soon. That's the production-honest choice for testing with real customers —
 * they see a real store about to open, not a dead button and not a broken
 * payment. When M2 lands, this component becomes the entry to the order form.
 *
 * A tiny client component so the rest of the card can stay server-rendered
 * (fast). Only THIS bit needs interactivity.
 */

import { useState } from "react";

export function OrderButton({ available }: { available: boolean }) {
  const [tapped, setTapped] = useState(false);

  if (!available) {
    return (
      <button
        disabled
        className="w-full rounded-lg bg-zinc-100 px-4 py-2.5 text-sm font-semibold text-zinc-400 dark:bg-zinc-800 dark:text-zinc-500"
      >
        Sold out
      </button>
    );
  }

  return (
    <div>
      <button
        onClick={() => setTapped(true)}
        className="w-full rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-emerald-700 active:bg-emerald-800"
      >
        Order via M-Pesa
      </button>
      {tapped && (
        <p
          role="status"
          className="mt-2 rounded-lg bg-emerald-50 px-3 py-2 text-center text-xs text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
        >
          🎉 Checkout is launching shortly — you&apos;ll pay securely with M-Pesa.
          Thanks for testing!
        </p>
      )}
    </div>
  );
}
