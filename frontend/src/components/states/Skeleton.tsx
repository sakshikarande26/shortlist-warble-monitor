// Fixed-height placeholders so nothing jumps once real content arrives.

export function SkeletonLine({ width = "w-2/3" }: { width?: string }) {
  return <div className={`h-4 ${width} animate-pulse rounded bg-black/[0.04]`} />;
}

export function SkeletonCard() {
  return (
    <div className="flex h-[132px] items-center gap-4 rounded-xl border border-line p-4">
      <div className="h-10 w-10 shrink-0 animate-pulse rounded-full bg-black/[0.04]" />
      <div className="flex-1 space-y-2">
        <div className="h-3 w-24 animate-pulse rounded bg-black/[0.04]" />
        <div className="h-4 w-3/4 animate-pulse rounded bg-black/[0.04]" />
        <div className="h-3 w-1/2 animate-pulse rounded bg-black/[0.04]" />
      </div>
      <div className="h-10 w-20 shrink-0 animate-pulse rounded bg-black/[0.04]" />
    </div>
  );
}

export function SkeletonChart() {
  return <div className="h-[280px] w-full animate-pulse rounded-xl border border-line bg-black/[0.03]" />;
}
