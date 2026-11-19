"use client";

import {useRef, useState, type FormEvent} from "react";
import {Button} from "@/components/ui/button";
import {Field} from "@/components/ui/primitives";
import {workspaceFetch, workspacePath} from "@/lib/workspace-path";

async function workspaceSession(method: "POST" | "DELETE", fields?: {email: string; password: string}) {
  const response = await workspaceFetch("/api/workspace-session", {
    method, ...(fields && {headers: {"Content-Type": "application/json"}, body: JSON.stringify(fields)}),
  });
  if (response.status === 204) return;
  const body = await response.json().catch(() => null);
  throw new Error(typeof body?.message === "string" ? body.message : "暂时无法连接，请稍后再试。");
}

export function PrivateSignInForm() {
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const running = useRef(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (running.current) return;
    const values = new FormData(event.currentTarget);
    running.current = true;
    setPending(true);
    setMessage("");
    try {
      await workspaceSession("POST", {email: String(values.get("email")), password: String(values.get("password"))});
      window.location.replace(workspacePath("/"));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "暂时无法登录。");
      running.current = false;
      setPending(false);
    }
  }
  return <form className="stack-md" method="post" onSubmit={submit}>
    <Field id="workspace-email" label="受邀邮箱"><input id="workspace-email" name="email" type="email" autoComplete="username" maxLength={254} required /></Field>
    <Field id="workspace-password" label="密码"><input id="workspace-password" name="password" type="password" autoComplete="current-password" maxLength={128} required /></Field>
    {message && <p className="jl-callout" data-tone="danger" role="alert">{message}</p>}
    <div className="jl-inline"><Button type="submit" disabled={pending}>{pending ? "正在登录…" : "登录个人工作台"}</Button></div>
  </form>;
}

export function PrivateSignOutButton() {
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const running = useRef(false);
  async function signOut() {
    if (running.current) return;
    running.current = true;
    setPending(true);
    setMessage("");
    try {
      await workspaceSession("DELETE");
      window.location.replace(workspacePath("/sign-in"));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "没能确认退出，请稍后再试。");
      running.current = false;
      setPending(false);
    }
  }
  return <div className="stack-sm">
    <Button type="button" variant="subtle" disabled={pending} onClick={() => void signOut()}>{pending ? "正在退出…" : "退出登录"}</Button>
    {message && <p role="alert">{message}</p>}
  </div>;
}
