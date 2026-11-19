"use client";

import * as Dialog from "@radix-ui/react-dialog";
import {useRef, useState, type ReactElement, type ReactNode} from "react";
import {Button} from "./button";

// Radix handles focus trap, Escape and restoring focus to the trigger.
export function ActionDialog({trigger, title, description, children, action, guardDraft = false}: {
  trigger: ReactElement; title: string; description: string; children: ReactNode; action?: ReactNode; guardDraft?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const resume = useRef<HTMLButtonElement>(null);
  const lastControl = useRef<HTMLElement | null>(null);
  function close() {
    setOpen(false); setDirty(false); setConfirmDiscard(false);
  }
  function change(value: boolean) {
    if (value) {setOpen(true); return;}
    if (guardDraft && dirty) {
      if (confirmDiscard) return;
      setConfirmDiscard(true);
      requestAnimationFrame(() => resume.current?.focus());
    } else close();
  }
  return <Dialog.Root open={open} onOpenChange={change}>
    <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
    <Dialog.Portal>
      <Dialog.Overlay className="jl-dialog-backdrop" />
      <Dialog.Content className="jl-panel jl-dialog">
        <Dialog.Title>{title}</Dialog.Title>
        <Dialog.Description className="jl-dialog-description">{description}</Dialog.Description>
        <div hidden={confirmDiscard} onFocusCapture={event => {
          if (event.target instanceof HTMLElement) lastControl.current = event.target;
        }} onChangeCapture={guardDraft ? () => setDirty(true) : undefined}>{children}</div>
        {confirmDiscard ? <div className="stack-sm">
          <p className="jl-callout" data-tone="warning" role="status">有尚未应用的修改。放弃后，原有筛选仍保留。</p>
          <div className="jl-dialog-footer">
            <Button ref={resume} onClick={() => {
              setConfirmDiscard(false);
              requestAnimationFrame(() => lastControl.current?.focus());
            }}>继续编辑</Button>
            <Button variant="secondary" onClick={close}>放弃修改</Button>
          </div>
        </div> : <div className="jl-dialog-footer">
          <Dialog.Close asChild><Button variant="secondary">{action ? "取消" : "关闭"}</Button></Dialog.Close>
          {action}
        </div>}
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
