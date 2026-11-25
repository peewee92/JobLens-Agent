const releasePattern = /^v?((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/;

export function releaseVersionLabel(configured: string | undefined, local: boolean): string | null {
  const version = configured?.trim().match(releasePattern)?.[1];
  return version ? `v${version}` : local ? "本地开发" : null;
}
