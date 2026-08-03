/** Shared presentational primitives. Every panel is built from these. */

import type { ReactNode } from "react";

import { ApiError } from "@/lib/api";

// ---- Card ----------------------------------------------------------------

export function Card({
  title,
  hint,
  action,
  flush,
  children,
  footer,
  className = "",
}: {
  title?: string;
  hint?: ReactNode;
  action?: ReactNode;
  flush?: boolean;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {title && (
        <header className="card__header">
          <h2 className="card__title">{title}</h2>
          {hint && <span className="card__hint">{hint}</span>}
          {action}
        </header>
      )}
      <div className={flush ? "card__body card__body--flush" : "card__body"}>{children}</div>
      {footer && <div className="card__footer">{footer}</div>}
    </section>
  );
}

// ---- Badge ---------------------------------------------------------------

export type Tone = "neutral" | "accent" | "success" | "warning" | "danger" | "info";

export function Badge({
  tone = "neutral",
  dot,
  children,
}: {
  tone?: Tone;
  dot?: boolean;
  children: ReactNode;
}) {
  return (
    <span className={`badge badge--${tone}`}>
      {dot && <span className="dot" />}
      {children}
    </span>
  );
}

// ---- Button --------------------------------------------------------------

export function Button({
  variant = "secondary",
  size,
  children,
  ...rest
}: {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm";
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={`btn btn--${variant} ${size ? `btn--${size}` : ""} ${rest.className ?? ""}`}
    >
      {children}
    </button>
  );
}

// ---- Loading / empty / error --------------------------------------------

export function Skeleton({ width = "100%", height = 14 }: { width?: string; height?: number }) {
  return <div className="skeleton" style={{ width, height }} aria-hidden />;
}

/**
 * Row-shaped loading state. It mirrors the real row layout so the panel does
 * not jump when data arrives.
 */
export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="list" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, index) => (
        <div className="list__row" key={index}>
          <div className="list__main stack" style={{ gap: 7 }}>
            <Skeleton width={`${86 - index * 9}%`} />
            <Skeleton width={`${48 - index * 5}%`} height={11} />
          </div>
          <Skeleton width="42px" height={11} />
        </div>
      ))}
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body?: string }) {
  return (
    <div className="state">
      <svg className="state__icon" width="26" height="26" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
        <path d="M8.5 13.5h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
      <p className="state__title">{title}</p>
      {body && <p className="state__body">{body}</p>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const offline = error instanceof ApiError && error.isOffline;
  const message =
    error instanceof Error ? error.message : "Something went wrong loading this panel.";

  return (
    <div className="state">
      <svg className="state__icon" width="26" height="26" viewBox="0 0 24 24" fill="none">
        <path
          d="M12 8.5v4M12 16h.01M10.3 3.9 2.5 17.4a2 2 0 0 0 1.7 3h15.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
      <p className="state__title">{offline ? "Propilot API is unreachable" : "Couldn’t load"}</p>
      <p className="state__body">
        {offline
          ? "Start the API with `make run`, then retry."
          : message}
      </p>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

/** Renders the right state for an async resource, so panels stay declarative. */
export function Async<T>({
  data,
  error,
  loading,
  onRetry,
  skeleton,
  empty,
  children,
}: {
  data: T | null;
  error: unknown;
  loading: boolean;
  onRetry?: () => void;
  skeleton?: ReactNode;
  empty?: { title: string; body?: string; when?: (data: T) => boolean };
  children: (data: T) => ReactNode;
}) {
  if (loading && data === null) return <>{skeleton ?? <SkeletonRows />}</>;
  if (error && data === null) return <ErrorState error={error} {...(onRetry ? { onRetry } : {})} />;
  if (data === null) return <EmptyState title="No data" />;
  if (empty?.when?.(data)) {
    return <EmptyState title={empty.title} {...(empty.body ? { body: empty.body } : {})} />;
  }
  return <>{children(data)}</>;
}

// ---- Misc ----------------------------------------------------------------

export function Score({ value }: { value: number }) {
  return (
    <span className="score" title={`Engagement score ${value}/100`}>
      <span className="score__bar">
        <span className="score__fill" style={{ width: `${Math.min(100, value)}%` }} />
      </span>
      <span>{value}</span>
    </span>
  );
}
