import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`border border-hairline rounded-xl bg-surface-card ${className}`}>
      {children}
    </div>
  );
}

export function CardHeader({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`flex items-center justify-between gap-3.5 px-6 py-4 border-b border-hairline ${className}`}>
      {children}
    </div>
  );
}
