export default function HomePage() {
  return (
    <div className="flex w-full max-w-md flex-1 flex-col items-center justify-center p-6 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-100 text-brand-700 shadow-sm dark:bg-brand-950 dark:text-brand-300">
        <svg
          className="h-8 w-8"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
          />
        </svg>
      </div>
      <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
        Smart Recycling Agent
      </h1>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
        Mobile scanner foundation initialized. Ready for Phase 2 implementation.
      </p>
    </div>
  );
}
