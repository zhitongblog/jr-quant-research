import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`bg-panel border border-border rounded-lg shadow-sm ${className}`}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  right,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="px-4 py-3 border-b border-border flex items-start justify-between">
      <div>
        <div className="text-sm font-medium text-fg">{title}</div>
        {subtitle && <div className="text-xs text-muted mt-0.5">{subtitle}</div>}
      </div>
      {right && <div className="text-xs text-muted">{right}</div>}
    </div>
  );
}

export function CardBody({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`p-4 ${className}`}>{children}</div>;
}

export function Pill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "up" | "down" | "accent";
}) {
  const colors = {
    neutral: "bg-panel-2 text-muted border-border",
    up: "bg-up/10 text-up border-up/30",
    down: "bg-down/10 text-down border-down/30",
    accent: "bg-accent/10 text-accent border-accent/30",
  } as const;
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-mono border ${colors[tone]}`}
    >
      {children}
    </span>
  );
}
