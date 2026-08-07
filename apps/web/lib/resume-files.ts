export const MAX_RESUME_FILE_BYTES = 5 * 1024 * 1024;

const SUPPORTED_RESUME_EXTENSIONS = [".pdf", ".docx"] as const;

export function validateResumeFile(file: Pick<File, "name" | "size">): string | null {
  const lowerName = file.name.trim().toLowerCase();
  const supported = SUPPORTED_RESUME_EXTENSIONS.some((extension) =>
    lowerName.endsWith(extension),
  );
  if (!supported) {
    return "仅支持 PDF 或 DOCX 文件。";
  }
  if (file.size <= 0) {
    return "文件为空，请重新选择。";
  }
  if (file.size > MAX_RESUME_FILE_BYTES) {
    return "文件超过 5 MiB，请压缩后再上传。";
  }
  return null;
}
