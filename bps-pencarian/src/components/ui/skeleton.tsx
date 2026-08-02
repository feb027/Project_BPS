/** Skeleton loading — placeholder abu-abu yang meniru layout hasil, lebih
    baik dari spinner untuk persepsi kecepatan. */
export function SkeletonBlock({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-muted/60 ${className}`} />
}

export function ResultSkeleton() {
  return (
    <div className="space-y-6">
      {/* Kartu jawaban langsung */}
      <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
        <SkeletonBlock className="h-4 w-40" />
        <SkeletonBlock className="mt-3 h-7 w-2/3" />
        <SkeletonBlock className="mt-4 h-48 w-full" />
        <div className="mt-4 flex gap-3">
          <SkeletonBlock className="h-8 w-24" />
          <SkeletonBlock className="h-8 w-24" />
        </div>
      </div>
      {/* Daftar tabel kandidat */}
      {[0, 1, 2].map((i) => (
        <div key={i} className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <div className="flex items-start gap-4">
            <SkeletonBlock className="h-10 w-10 shrink-0 rounded-md" />
            <div className="flex-1 space-y-2">
              <SkeletonBlock className="h-4 w-3/4" />
              <SkeletonBlock className="h-3 w-1/2" />
              <SkeletonBlock className="h-3 w-2/3" />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

export function ChartSkeleton() {
  return (
    <div className="flex-1 min-h-[420px] rounded-md border border-border bg-background p-6 flex flex-col gap-4">
      <div className="flex flex-wrap gap-3">
        <SkeletonBlock className="h-8 w-32" />
        <SkeletonBlock className="h-8 w-32" />
        <SkeletonBlock className="h-8 w-40" />
      </div>
      <SkeletonBlock className="h-[320px] w-full" />
    </div>
  )
}
