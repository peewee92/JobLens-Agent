# ADR-0017: Resume document parsing and privacy boundary

## Status

Accepted

## Context

JobLens already accepts pasted resume text and produces an Evidence-grounded Profile Proposal. Real users usually have PDF or DOCX resumes, but passing arbitrary document bytes directly to an LLM would mix file parsing, AI extraction, privacy and confirmed facts in one unsafe boundary.

PDF extraction also has known limits: image-only documents require OCR, and expanded page content can consume significantly more memory than the uploaded file. DOCX is a ZIP/XML container and cannot be trusted from its extension alone.

## Decision

Add a deterministic document-input layer before the existing Profile Proposal Workflow:

```text
multipart upload
→ bounded byte read
→ ResumeDocumentParser Port
→ PDF/DOCX Adapter
→ normalized text quality gate
→ existing Profile Proposal Workflow
→ Trace
→ user review
```

### Supported formats

- text-based PDF;
- DOCX containing `word/document.xml`.

OCR, encrypted PDF passwords and legacy DOC are excluded.

### Limits

- 5 MiB uploaded bytes;
- 20 PDF pages;
- 4 MiB expanded page content per PDF page;
- 10 MiB relevant DOCX XML;
- 50–30,000 normalized extracted characters.

### Detection

The parser evaluates filename extension, declared content type and actual structure:

- PDF must begin with `%PDF-`;
- DOCX must be a ZIP containing `word/document.xml`.

A renamed binary is rejected with 415.

### DOCX implementation

Use Python standard-library `zipfile` and `xml.etree.ElementTree` to extract top-level paragraphs and table rows in document order. This avoids adding a large document object model dependency for the MVP requirement.

### PDF implementation

Use `pypdf` for text extraction and encryption/page handling. Image-only PDFs return a stable text-not-extractable error instead of silently producing an empty Profile.

### Privacy

The original file bytes are request-scoped only. They are not persisted, logged or written to Trace. The existing Profile Proposal Workflow records the normalized text hash, character count and structured Proposal output.

### Confirmation boundary

Document parsing still produces only a Proposal. Neither the parser, document workflow nor file API can call `SaveProfileUseCase`. The user must adopt the Proposal into the edit form and explicitly save a confirmed Profile version.

## Consequences

### Positive

- lower onboarding friction for users with existing resumes;
- one extraction/grounding/Trace path for text, PDF and DOCX;
- deterministic parser tests independent of an LLM;
- explicit handling of scanned PDFs and forged files;
- no original document retention.

### Trade-offs

- complex PDF layout may produce imperfect reading order;
- DOCX text boxes, tracked changes, headers and embedded objects are not guaranteed;
- no OCR means scanned resumes are rejected;
- in-process PDF parsing still requires conservative limits.

## Alternatives rejected

### Send the original file directly to the model

Rejected because it couples provider-specific file handling to the product workflow, weakens reproducibility and makes privacy/grounding harder to audit.

### Implement OCR in the same slice

Rejected because OCR is a distinct AI capability requiring provider decisions, Eval, Trace, cost and privacy controls.

### Persist uploaded resumes

Rejected for MVP because Proposal generation does not require file history, while retention introduces sensitive-data lifecycle and permission requirements.
