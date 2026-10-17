# File attachments (v1)

Assembly supports **text-only attachments** for a single investigation. These contents are processed in memory as untrusted prompt data; they are not written to the backend filesystem or server database.

## Supported formats

Supported extensions: TXT, Markdown, CSV, JSON, LOG, Python, JavaScript/JSX, TypeScript/TSX, HTML, CSS, YAML, TOML, INI/CFG/CONF, XML, SQL, shell/PowerShell/batch scripts, and `.env.example`.

The request must be UTF-8 text. JSON files must parse as JSON and CSV is checked with a bounded row count. Binary files and other formats—including PDF, DOCX, images and OCR inputs—are not supported in v1. A file extension or MIME type is a validation hint, not a trust signal.

## Limits

- Up to **5 files** per investigation.
- **256 KiB per file** and **384 KiB combined**.
- Filenames are reduced to safe basenames and must be unique within the request.
- Prompt context is limited to **24,000 characters**. When the combined document context exceeds that budget, later content can be truncated; the user should attach only relevant excerpts for large documents.

The browser checks files for a quick user-facing error. The API repeats all validation server-side. Do not rely on client checks for security.

## Privacy and retention

- File text travels in the user's `POST /api/run` request and is held in backend memory for that run.
- The attachment text is provided to the investigation agents as bounded, clearly delimited untrusted context. The original question, not the file body, is used for external search queries.
- The web backend does not persist file bodies, names, or content to its server database or disk, and file text must not be included in logs, run events, or error responses.
- Browser run history may store display metadata (sanitized filename, normalized media type and size) but **never stores the original file content**. Site/browser data clearing can remove the metadata.
- Selected AI providers necessarily receive relevant prompt text as part of the model request. Their own data handling policies apply. Do not upload secrets or sensitive/confidential material unless you have reviewed the provider's policy and have a valid reason to share it.

## Prompt-injection handling

Attachments are untrusted data, not instructions. The application escapes the trusted prompt delimiters, uses a clear untrusted-content block and scans for common instruction-override patterns as a warning tripwire. Detection is not a proof of safety: models can still misunderstand or follow hostile text. Do not treat a scan result as a security guarantee.
