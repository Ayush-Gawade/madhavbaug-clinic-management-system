/** Skeleton loaders matching the shapes of the real content they replace. */

export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>): JSX.Element {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-lg bg-line ${className ?? ""}`}
      {...props}
    />
  );
}

export function SkeletonText({ lines = 3 }: { lines?: number }): JSX.Element {
  return (
    <div className="space-y-2">
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton
          key={index}
          className={index === lines - 1 ? "h-4 w-2/3" : "h-4 w-full"}
        />
      ))}
    </div>
  );
}

export function SkeletonTable({
  rows = 6,
  cols = 5,
}: {
  rows?: number;
  cols?: number;
}): JSX.Element {
  return (
    <div className="space-y-0">
      <div className="flex gap-4 border-b border-line px-5 py-3">
        {Array.from({ length: cols }, (_, index) => (
          <Skeleton key={index} className="h-3 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }, (_, rowIndex) => (
        <div key={rowIndex} className="flex items-center gap-4 border-b border-line/60 px-5 py-3.5">
          {Array.from({ length: cols }, (_, colIndex) => (
            <Skeleton
              key={colIndex}
              className={colIndex === 1 ? "h-4 flex-[2]" : "h-4 flex-1"}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
