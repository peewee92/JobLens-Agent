"use client";

import {useEffect, useRef, useState, type FormEvent} from "react";
import {Button} from "@/components/ui/button";
import {Field} from "@/components/ui/primitives";
import type {WorkspaceSignIn} from "@/lib/private-sign-in";
import {workspaceFetch, workspacePath} from "@/lib/workspace-path";

async function workspaceSession(method: "POST" | "DELETE", fields?: WorkspaceSignIn) {
  const response = await workspaceFetch("/api/workspace-session", {
    method, ...(fields && {headers: {"Content-Type": "application/json"}, body: JSON.stringify(fields)}),
  });
  if (response.status === 204) return "";
  const body = await response.json().catch(() => null);
  if (response.status === 202 && typeof body?.message === "string") return body.message;
  throw new Error(typeof body?.message === "string" ? body.message : "暂时无法连接，请稍后再试。");
}

export function PrivateSignInForm({codeEnabled}: {codeEnabled: boolean}) {
  const [mode, setMode] = useState<"code" | "password">(codeEnabled ? "code" : "password");
  const [emailSent, setEmailSent] = useState("");
  const [notice, setNotice] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const running = useRef(false);
  const emailField = useRef<HTMLInputElement>(null);
  const codeField = useRef<HTMLInputElement>(null);
  const passwordField = useRef<HTMLInputElement>(null);
  const codeStep = mode === "code" && Boolean(emailSent);
  useEffect(() => {
    if (codeStep) codeField.current?.focus();
  }, [codeStep]);
  function resetMode(nextMode: "code" | "password") {
    setMode(nextMode);
    setEmailSent("");
    setNotice("");
    setMessage("");
    emailField.current?.focus();
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (running.current) return;
    const values = new FormData(event.currentTarget);
    running.current = true;
    setPending(true);
    setMessage("");
    const email = String(values.get("email"));
    try {
      if (mode === "code" && !emailSent) {
        setNotice(await workspaceSession("POST", {mode: "send-code", email}));
        setEmailSent(email);
        running.current = false;
        setPending(false);
        return;
      }
      await workspaceSession("POST", mode === "code"
        ? {mode: "verify-code", email: emailSent, code: String(values.get("code"))}
        : {mode: "password", email, password: String(values.get("password"))});
      window.location.replace(workspacePath("/"));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "暂时无法登录。");
      running.current = false;
      setPending(false);
      (codeStep ? codeField.current : mode === "password" ? passwordField.current : emailField.current)?.focus();
    }
  }
  const action = mode === "password" || codeStep ? "登录个人工作台" : "获取邮箱验证码";
  return <form className="jl-private-sign-in-form" method="post" onSubmit={submit}>
    <Field id="workspace-email" label="受邀邮箱"><input ref={emailField} id="workspace-email" name="email" type="email" autoComplete="username" maxLength={254} required readOnly={pending || codeStep} /></Field>
    {mode === "password" && <Field id="workspace-password" label="密码"><input ref={passwordField} id="workspace-password" name="password" type="password" autoComplete="current-password" maxLength={128} required /></Field>}
    {codeStep && <Field id="workspace-code" label="邮件中的 6 位验证码"><input ref={codeField} id="workspace-code" name="code" type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required /></Field>}
    {notice && <p className="jl-callout" role="status">{notice}</p>}
    {message && <p className="jl-callout" data-tone="danger" role="alert">{message}</p>}
    <div className="jl-inline jl-private-sign-in-actions">
      <Button type="submit" disabled={pending}>{pending ? "正在处理…" : action}</Button>
      {codeStep && <Button type="button" variant="subtle" disabled={pending} onClick={() => resetMode("code")}>修改邮箱或重新获取验证码</Button>}
      {codeEnabled && <Button type="button" variant="subtle" disabled={pending} onClick={() => resetMode(mode === "code" ? "password" : "code")}>
        {mode === "code" ? "使用密码" : "使用邮箱验证码"}
      </Button>}
    </div>
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
