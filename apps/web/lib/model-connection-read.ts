export type ModelConnectionConfig = {
  enableThinking?: boolean | null;
  name: string;
  baseUrl: string;
  model: string;
  apiStyle: string;
  profileModel?: string;
  requirementModel?: string;
  semanticModel?: string;
};
export type ModelConnectionStatus = {
  recentCalls: {actionId: string; kind: string; status: string; model: string; attempts: number; inputTokens: number | null; outputTokens: number | null}[];
  connected: boolean;
  version: number;
  connection: ModelConnectionConfig | null;
  seed: string;
};

type ReadResult = {kind: "ready"; status: ModelConnectionStatus | null} | {kind: "unavailable"};
type Attempt = ReadResult | {kind: "retry"};
const unavailable = {kind: "unavailable"} as const;
const retry = {kind: "retry"} as const;

function isStatus(value: unknown): value is ModelConnectionStatus {
  const status = value as Partial<ModelConnectionStatus> | null;
  return !!status && typeof status.connected === "boolean" && Number.isInteger(status.version)
    && (status.seed === "blank" || status.seed === "sample") && Array.isArray(status.recentCalls)
    && (status.connected ? !!status.connection && typeof status.connection === "object" : status.connection === null);
}

async function readOnce(signal: AbortSignal, fetchStatus: typeof fetch): Promise<Attempt> {
  let response: Response;
  try {
    response = await fetchStatus("/api/byok/model-connection", {
      method: "GET",
      cache: "no-store",
      signal: AbortSignal.any([signal, AbortSignal.timeout(55_000)]),
    });
  } catch {
    return retry;
  }
  if ([502, 503, 504].includes(response.status)) return retry;

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    // Render can return an HTML startup page instead of the API response.
    return response.ok ? retry : unavailable;
  }
  if (response.ok) return isStatus(data) ? {kind: "ready", status: data} : unavailable;

  const code = (data as {error?: {code?: string}} | null)?.error?.code;
  if ((response.status === 410 && code === "demo_session_expired") ||
      (response.status === 403 && (code === "byok_required" || code === "demo_route_disabled"))) {
    return {kind: "ready", status: null};
  }
  return unavailable;
}

function waitForRetry(signal: AbortSignal, delayMs: number): Promise<void> {
  if (signal.aborted) return Promise.resolve();
  return new Promise(resolve => {
    const timer = setTimeout(finish, delayMs);
    function finish() {
      clearTimeout(timer);
      signal.removeEventListener("abort", finish);
      resolve();
    }
    signal.addEventListener("abort", finish, {once: true});
  });
}

/** Only read access can be retried. Each check ends after at most two attempts. */
export async function readModelConnection(
  signal: AbortSignal, fetchStatus = fetch, retryDelayMs = 2_000,
): Promise<ReadResult> {
  if (signal.aborted) return unavailable;
  const first = await readOnce(signal, fetchStatus);
  if (signal.aborted) return unavailable;
  if (first.kind !== "retry") return first;

  await waitForRetry(signal, retryDelayMs);
  if (signal.aborted) return unavailable;
  const second = await readOnce(signal, fetchStatus);
  return signal.aborted || second.kind === "retry" ? unavailable : second;
}
