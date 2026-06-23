import * as React from "react";
import { cn } from "../../lib/utils";
import { cva, type VariantProps } from "class-variance-authority";

const emButtonVariants = cva(
  [
    "inline-flex items-center justify-center",
    "select-none whitespace-nowrap",
    "border",
    "font-extrabold uppercase tracking-[0.04em]",
    "transition-all duration-150",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400",
    "disabled:pointer-events-none disabled:opacity-50",
    "cursor-pointer",
  ],
  {
    variants: {
      variant: {
        viewAll: [
          "h-10 px-6",
          "rounded-[2px]",
          "border-slate-700/70",
          "bg-[#272b33]",
          "text-[15px] text-slate-200",
          "shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_1px_0_rgba(0,0,0,0.45)]",
          "hover:bg-[#303642]",
          "active:translate-y-px active:bg-[#222730]",
        ],
        ghost: ["h-9 px-4", "rounded-md border-transparent", "bg-transparent", "text-slate-300", "hover:bg-slate-800 hover:text-slate-100"],
        danger: ["h-9 px-4", "rounded-md", "border-red-800/70", "bg-red-950", "text-red-100", "hover:bg-red-900"],
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "",
        lg: "h-11 px-8 text-base",
      },
    },
    defaultVariants: {
      variant: "viewAll",
      size: "md",
    },
  },
);

export type EmButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof emButtonVariants>;

export function EmButton({ className, variant, size, type = "button", ...props }: EmButtonProps) {
  return (
    <button
      type={type}
      className={cn(emButtonVariants({ variant, size }), className)}
      {...props}
    />
  );
}
