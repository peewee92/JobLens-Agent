"use client";

import * as Dialog from "@radix-ui/react-dialog";
import React, {type ReactElement, type ReactNode} from "react";
import {Button} from "./button";

// Structure follows the shadcn/ui Radix Dialog pattern; Radix owns focus trapping and restoration.
export function ActionDialog({trigger, title, description, children}: {
  trigger: ReactElement; title: string; description: string; children: ReactNode;
}) {
  return <Dialog.Root>
    <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
    <Dialog.Portal>
      <Dialog.Overlay className="jl-dialog-backdrop" />
      <Dialog.Content className="jl-panel jl-dialog">
        <Dialog.Title>{title}</Dialog.Title>
        <Dialog.Description className="jl-dialog-description">{description}</Dialog.Description>
        {children}
        <div className="jl-inline">
          <Dialog.Close asChild><Button variant="secondary">关闭</Button></Dialog.Close>
        </div>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
