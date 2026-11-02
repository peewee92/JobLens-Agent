/** Accept labels only for requested identities; failed reads stay identifiable by ID. */
export function validatedRunLabels(ids: readonly string[], body: unknown): Record<string, string> {
  const requested = new Set(ids);
  if (!body || typeof body !== "object" || !Array.isArray((body as {items?: unknown}).items)) return {};
  return Object.fromEntries((body as {items: unknown[]}).items.flatMap(item => {
    if (!item || typeof item !== "object") return [];
    const {id, title} = item as {id?: unknown; title?: unknown};
    return typeof id === "string" && requested.has(id) && typeof title === "string" && title.trim()
      ? [[id, title] as const] : [];
  }));
}
