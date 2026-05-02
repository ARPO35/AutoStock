import type { ReactNode, InputHTMLAttributes, TextareaHTMLAttributes, SelectHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  icon?: ReactNode;
}

export function Input({ label, icon, className = "", ...props }: InputProps) {
  return (
    <label className="grid gap-1.5 text-xs text-text-muted">
      {label}
      <span className="relative block">
        {icon && (
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted">
            {icon}
          </span>
        )}
        <input
          className={`w-full h-10 px-3 rounded-lg bg-surface-card border border-hairline text-text-on-dark placeholder:text-text-muted focus:border-info focus:ring-2 focus:ring-info/50 ${icon ? "pl-8" : ""} ${className}`}
          {...props}
        />
      </span>
    </label>
  );
}

export function Select({ className = "", ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={`w-full h-10 px-3 rounded-md bg-surface-card border border-hairline text-text-on-dark focus:border-info focus:ring-2 focus:ring-info/50 ${className}`}
      {...props}
    />
  );
}

export function Textarea({ className = "", ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={`w-full min-h-[78px] resize-y px-3 py-2.5 rounded-lg bg-surface-card border border-hairline text-text-on-dark placeholder:text-text-muted focus:border-info focus:ring-2 focus:ring-info/50 leading-relaxed ${className}`}
      {...props}
    />
  );
}
