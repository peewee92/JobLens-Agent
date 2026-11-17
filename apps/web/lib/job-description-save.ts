export const descriptionSavedQuery = "savedDescription";

export function isDescriptionRevision(value: unknown): value is string {
  return typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
}

/** Stay on the same posting and preserve the explicit analysis scope or history view. */
export function confirmedDescriptionHref(current: URL, revision: string): string {
  const query = new URLSearchParams(current.search);
  query.set(descriptionSavedQuery, revision);
  return `${current.pathname}?${query}#job-description`;
}
