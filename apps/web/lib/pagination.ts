/** Page math for existing offset/limit APIs. A missing total stays unknown. */
export function lastPageOffset(total: number, limit: number): number {
  return Math.max(0, Math.ceil(total / limit) - 1) * limit;
}

export function pageWindow(offset: number, limit: number, total?: number) {
  const current = Math.floor(offset / limit) + 1;
  const last = total === undefined ? undefined : Math.max(1, Math.ceil(total / limit));
  const numbers = last === undefined ? [] : Array.from(new Set([1, current - 1, current, current + 1, last]))
    .filter(number => number > 0 && number <= last).sort((a, b) => a - b);
  return {current, last, numbers};
}

export function parsePageOffset(value: string | string[] | undefined): number {
  return typeof value === "string" && /^\d{1,6}$/.test(value) ? Number(value) : 0;
}

/** One read-only recovery when a bookmarked page is no longer present. */
export async function readKnownPage<T extends {total: number; items: readonly unknown[]}>(
  offset: number, limit: number, read: (offset: number) => Promise<T>,
) {
  const page = await read(offset);
  const last = lastPageOffset(page.total, limit);
  if (offset && last < offset && page.items.length === 0) {
    return {page: await read(last), offset: last, adjusted: true};
  }
  return {page, offset, adjusted: false};
}
