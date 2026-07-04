"use client";

import * as React from "react";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type ToastVariant = "default" | "success" | "error" | "warning";

export interface ToastOptions {
  title: string;
  description?: string;
  variant?: ToastVariant;
  /** Milliseconds before auto-dismiss. Defaults to 5000. */
  duration?: number;
  /** Optional action rendered on the right side of the toast. */
  action?: { label: string; onClick: () => void };
}

interface ToastItem extends ToastOptions {
  id: number;
}

interface ToastContextValue {
  toast: (options: ToastOptions) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

const VARIANT_STYLES: Record<ToastVariant, { border: string; icon: React.ReactNode }> = {
  default: {
    border: "border-slate-200",
    icon: <Info className="h-4 w-4 text-[#1b59f8]" />,
  },
  success: {
    border: "border-emerald-200",
    icon: <CheckCircle2 className="h-4 w-4 text-emerald-600" />,
  },
  error: {
    border: "border-red-200",
    icon: <AlertTriangle className="h-4 w-4 text-red-600" />,
  },
  warning: {
    border: "border-orange-200",
    icon: <AlertTriangle className="h-4 w-4 text-orange-500" />,
  },
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<ToastItem[]>([]);
  const idRef = React.useRef(0);

  const toast = React.useCallback((options: ToastOptions) => {
    idRef.current += 1;
    const item: ToastItem = { id: idRef.current, ...options };
    setToasts((prev) => [...prev.slice(-4), item]);
  }, []);

  const dismiss = React.useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      <ToastPrimitive.Provider swipeDirection="right">
        {children}
        {toasts.map((t) => {
          const style = VARIANT_STYLES[t.variant ?? "default"];
          return (
            <ToastPrimitive.Root
              key={t.id}
              duration={t.duration ?? 5000}
              onOpenChange={(open) => {
                if (!open) dismiss(t.id);
              }}
              className={cn(
                "pointer-events-auto flex items-start gap-3 rounded-xl border bg-white p-4 shadow-lg",
                "data-[state=open]:animate-in data-[state=open]:slide-in-from-right",
                "data-[state=closed]:animate-out data-[state=closed]:fade-out-80",
                style.border,
              )}
            >
              <div className="mt-0.5 shrink-0">{style.icon}</div>
              <div className="min-w-0 flex-1">
                <ToastPrimitive.Title className="text-sm font-semibold text-slate-900">
                  {t.title}
                </ToastPrimitive.Title>
                {t.description && (
                  <ToastPrimitive.Description className="mt-0.5 text-xs text-slate-500 break-words">
                    {t.description}
                  </ToastPrimitive.Description>
                )}
                {t.action && (
                  <ToastPrimitive.Action altText={t.action.label} asChild>
                    <button
                      onClick={t.action.onClick}
                      className="mt-2 text-xs font-semibold text-[#1b59f8] hover:underline"
                    >
                      {t.action.label}
                    </button>
                  </ToastPrimitive.Action>
                )}
              </div>
              <ToastPrimitive.Close className="shrink-0 rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600">
                <X className="h-3.5 w-3.5" />
              </ToastPrimitive.Close>
            </ToastPrimitive.Root>
          );
        })}
        <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2 outline-none" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}
