import assert from "node:assert/strict";
import {readFile, readdir} from "node:fs/promises";
import {join, resolve} from "node:path";
import test from "node:test";

const webRoot = resolve(import.meta.dirname, "..");

async function sourceFiles(directory: string): Promise<string[]> {
  const entries = await readdir(directory, {withFileTypes: true});
  const nested = await Promise.all(
    entries.map(async (entry) => {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) return sourceFiles(path);
      return /\.(ts|tsx)$/.test(entry.name) ? [path] : [];
    }),
  );
  return nested.flat();
}

test("browser-facing source never exposes the backend URL as NEXT_PUBLIC", async () => {
  const files = [
    ...(await sourceFiles(join(webRoot, "app"))),
    ...(await sourceFiles(join(webRoot, "components"))),
    ...(await sourceFiles(join(webRoot, "lib"))),
  ];
  for (const file of files) {
    const source = await readFile(file, "utf8");
    assert.doesNotMatch(source, /NEXT_PUBLIC_JOBLENS_BACKEND_URL/, file);
  }
});

test("the import Client Component calls only the same-origin proxy", async () => {
  const source = await readFile(join(webRoot, "components/import-form.tsx"), "utf8");
  assert.match(source, /fetch\("\/api\/job-imports"/);
  assert.doesNotMatch(source, /JOBLENS_BACKEND_URL|127\.0\.0\.1:8000/);
});

test("the Profile Client Component calls only same-origin proxies", async () => {
  const source = await readFile(join(webRoot, "components/profile-editor.tsx"), "utf8");
  assert.match(source, /fetch\("\/api\/profile"/);
  assert.match(source, /fetch\("\/api\/search-intent"/);
  assert.doesNotMatch(source, /JOBLENS_BACKEND_URL|127\.0\.0\.1:8000/);
});

test("the Resume Proposal Client Component calls only the same-origin proxy", async () => {
  const source = await readFile(
    join(webRoot, "components/resume-proposal-panel.tsx"),
    "utf8",
  );
  assert.match(source, /fetch\("\/api\/profile-proposals"/);
  assert.match(source, /fetch\("\/api\/profile-proposals\/file"/);
  assert.doesNotMatch(source, /JOBLENS_BACKEND_URL|127\.0\.0\.1:8000/);
  assert.doesNotMatch(source, /fetch\("\/api\/profile"/);
});

test("the Profile Eval Review Client calls only its same-origin command proxy", async () => {
  const source = await readFile(
    join(webRoot, "components/profile-eval-review-form.tsx"),
    "utf8",
  );
  assert.match(source, /fetch\(\s*`\/api\/profile-evals\/\$\{encodeURIComponent\(run\.id\)\}\/review`/);
  assert.doesNotMatch(source, /JOBLENS_BACKEND_URL|127\.0\.0\.1:8000/);
  assert.doesNotMatch(source, /profile-proposals|run_profile_eval|OPENAI_API_KEY/);
});

test("Profile Eval pages consume review facts instead of implementing backend policy", async () => {
  const listPage = await readFile(join(webRoot, "app/evals/profile/page.tsx"), "utf8");
  const detailPage = await readFile(
    join(webRoot, "app/evals/profile/[id]/page.tsx"),
    "utf8",
  );
  for (const source of [listPage, detailPage]) {
    assert.doesNotMatch(source, /fetch\(/);
    assert.doesNotMatch(source, /JOBLENS_BACKEND_URL/);
  }
});

test("public contract types exclude raw and internal stream fields", async () => {
  const source = await readFile(join(webRoot, "lib/contracts.ts"), "utf8");
  for (const forbidden of [
    "sourceRaw",
    "candidateRaw",
    "canonicalKey",
    "normalizedSourceUrl",
    "profileKey",
    "intentKey",
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});
