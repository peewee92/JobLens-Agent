import assert from "node:assert/strict";
import test from "node:test";

import {MAX_RESUME_FILE_BYTES, validateResumeFile} from "@/lib/resume-files";

test("resume file validation accepts PDF and DOCX within the upload limit", () => {
  assert.equal(validateResumeFile({name: "resume.pdf", size: 1024}), null);
  assert.equal(validateResumeFile({name: "RESUME.DOCX", size: MAX_RESUME_FILE_BYTES}), null);
});

test("resume file validation rejects unsupported empty and oversized files", () => {
  assert.equal(validateResumeFile({name: "resume.txt", size: 1024}), "仅支持 PDF 或 DOCX 文件。");
  assert.equal(validateResumeFile({name: "resume.pdf", size: 0}), "文件为空，请重新选择。");
  assert.equal(
    validateResumeFile({name: "resume.docx", size: MAX_RESUME_FILE_BYTES + 1}),
    "文件超过 5 MiB，请压缩后再上传。",
  );
});
