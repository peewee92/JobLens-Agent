# Resume Document Proposal API Contract

## Goal

Allow a user to upload a PDF or DOCX resume and reuse the existing grounded Profile Proposal workflow:

```text
file upload
→ bounded read
→ document parser
→ normalized resume text
→ Profile Proposal Workflow
→ Trace
→ user review
→ explicit confirmed Profile save
```

The document endpoint never writes a confirmed Profile.

## Endpoint

```http
POST /api/v1/profile-proposals/file
Content-Type: multipart/form-data
```

Form field:

- `file`: one PDF or DOCX resume.

Success returns the existing `ProfileExtractionProposal` response used by `POST /api/v1/profile-proposals`.

## Supported documents

| Format | Extension | Accepted media types | Required signature |
| --- | --- | --- | --- |
| PDF | `.pdf` | `application/pdf` or absent/generic | `%PDF-` |
| DOCX | `.docx` | Office Open XML or absent/generic | ZIP containing `word/document.xml` |

Extension, declared content type and actual structure are considered together. A renamed binary is rejected.

## Limits

- maximum uploaded bytes: 5 MiB;
- maximum PDF pages: 20;
- maximum expanded PDF page content: 4 MiB per page;
- maximum relevant DOCX XML expansion: 10 MiB;
- extracted text: 50–30,000 characters after normalization.

The original file is held only for request processing. It is not persisted to the database or Trace.

## Error semantics

| Scenario | HTTP | Code |
| --- | ---: | --- |
| missing/empty file | 422 | `invalid_resume_document` |
| file exceeds 5 MiB | 413 | `resume_document_too_large` |
| unsupported/forged type | 415 | `unsupported_resume_document` |
| corrupt PDF/DOCX | 422 | `invalid_resume_document` |
| encrypted PDF | 422 | `invalid_resume_document` |
| page/expanded-content limit exceeded | 422 | `invalid_resume_document` |
| no usable text / scanned image PDF | 422 | `resume_text_not_extractable` |
| extractor disabled | 503 | `profile_extractor_unavailable` |
| extractor provider failure | 502 | `profile_extractor_failed` |
| ungrounded provider output | 502 | `invalid_profile_extractor_output` |

## Privacy boundary

The following must not be written to Trace or ordinary logs:

- original PDF/DOCX bytes;
- base64 file content;
- complete multipart body;
- API credentials.

The existing Profile Proposal Workflow records only the normalized text hash, character count and structured proposal output.

## OCR boundary

OCR is not part of this slice. An image-only/scanned PDF that yields insufficient text returns `resume_text_not_extractable`. OCR must be introduced later as a separate capability with its own provider, Eval, Trace and privacy decisions.

## Completion evidence

- parser unit tests for PDF and DOCX;
- forged type, encrypted/empty PDF and size-limit tests;
- API tests proving file Proposal does not create a confirmed Profile;
- Trace negative assertions proving file bytes are absent;
- Web same-origin upload path;
- real FastAPI + production Next smoke flow;
- existing text Proposal tests remain green.
