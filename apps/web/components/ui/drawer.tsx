"use client";

import * as Dialog from "@radix-ui/react-dialog";
import type {ReactElement, ReactNode} from "react";
import {Button} from "./button";

export function DetailDrawer({trigger, title, description, children, onOpenChange}: {
  trigger: ReactElement; title: string; description: string; children: ReactNode; onOpenChange?: (open: boolean) => void;
}) {
  return <Dialog.Root onOpenChange={onOpenChange}>
    <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
    <Dialog.Portal>
      <Dialog.Overlay className="jl-dialog-backdrop" />
      <Dialog.Content className="jl-drawer">
        <header className="jl-drawer-header">
          <div>
            <Dialog.Title>{title}</Dialog.Title>
            <Dialog.Description className="jl-dialog-description">{description}</Dialog.Description>
          </div>
          <Dialog.Close asChild><Button variant="secondary">返回<span className="sr-only">原列表</span></Button></Dialog.Close>
        </header>
        <div className="jl-drawer-body">{children}</div>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
