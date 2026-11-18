import {clsx} from "clsx";
import {twMerge} from "tailwind-merge";
import {Slot} from "@radix-ui/react-slot";
import {cva, type VariantProps} from "class-variance-authority";
import React, {type ComponentProps} from "react";

export const buttonVariants = cva(
  "inline-flex min-h-11 max-w-full items-center justify-center gap-2 rounded-lg border border-solid px-4 py-2 text-center text-sm leading-5 font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60",
  {variants: {variant: {
    primary: "border-jl-brand bg-jl-brand text-white hover:bg-jl-brand-hover",
    secondary: "border-jl-line bg-jl-panel text-jl-ink hover:bg-jl-soft",
    subtle: "border-transparent bg-transparent text-jl-brand-hover hover:bg-jl-accent",
  }}, defaultVariants: {variant: "primary"}},
);

type Props = ComponentProps<"button"> & VariantProps<typeof buttonVariants> & {asChild?: boolean};

// shadcn/ui Button pattern: variants plus Radix Slot; never nest a link inside a button.
export function Button({asChild, variant, className, type, ref, ...props}: Props) {
  const style = twMerge(clsx(buttonVariants({variant}), className));
  if (asChild) return <Slot ref={ref} className={style} {...props} />;
  return <button ref={ref} className={style} type={type ?? "button"} {...props} />;
}
