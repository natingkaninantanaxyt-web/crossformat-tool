# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository overview

This repo contains a single self-contained HTML file, `crossformatstep.html`. It is a client-side "CrossFormat" tool that converts Excel shop-registration files into a pipe-delimited `.txt` format for a partner's QR API onboarding pipeline, validating structure along the way. There is no build system, package manager, test suite, or server — the file is opened directly in a browser.

## Running / developing

- Open `crossformatstep.html` directly in a browser (e.g. `open crossformatstep.html` on macOS). No install step, no dev server, no bundler.
- All dependencies are loaded from CDNs in `<head>`: SheetJS (`xlsx@0.18.5`) for Excel parsing, Font Awesome for icons, Google Fonts (Inter/Outfit/JetBrains Mono). An internet connection is required for the page to render/function correctly.
- Since it's a single static file, "testing" a change means reloading the file in the browser and manually running the converter with sample `.xlsx`/`.xls` files.

## Architecture

Everything lives in one file, split into three parts: `<style>` (CSS custom properties + component styles, dark theme only), the HTML markup (two tabs), and one `<script>` block containing all app logic. There is no module system — all functions are global and wired up via `document.addEventListener`/`getElementById` in `initEventListeners`/`initDragAndDrop`/`initSettingsPanel`, called from a single `DOMContentLoaded` handler.

### Global state

A single `state` object holds everything: the two header templates (`templateRow1`, `templateRow3`), the list of uploaded files (each with parsed `rows`, a `status` of `passed`/`error`, and `logs`), the generated `outputText`, and `outputIssues`/`outputStats` from output verification. Templates persist to `localStorage` under `df_template_row1_arr` / `df_template_row3_arr` (see `loadTemplate`/`saveTemplate`); everything else is in-memory only and resets on reload.

### Expected Excel layout

Uploaded workbooks (first sheet only) are expected to follow a fixed 4-row-plus structure:
- **Row 1** (index 0): global header *names* — validated against `state.templateRow1` (default: `recordType, functionName, fileDate, fileNum, partnerID, totalRecordNum`).
- **Row 2** (index 1): global header *values* — only Row 2 of the **first** valid file is used for output. `fileDate`, `partnerID`, and `totalRecordNum` in this row are overridden at output time from the UI's date picker / partner-ID input / computed record count (see `generateOutputText`).
- **Row 3** (index 2): shop-data column *names* — validated against `state.templateRow3` (a much larger list of ~60 columns, many with Thai-language descriptions embedded in the header string itself, e.g. `"addressNo\n(M)\n(เลขที่ตั้งสาขา)"`).
- **Row 4+** (index 3+): shop-data *values*, one row per shop record. Empty rows (`isRowEmpty`) are skipped. These rows are pulled from **every** valid uploaded file, not just the first.

### Conversion & validation pipeline

`handleExcelFiles` → parses each file with `XLSX.utils.sheet_to_json(sheet, {header: 1})` and pushes a raw record into `state.uploadedFiles`, then calls `processUploadedFiles`, which is the central pipeline re-run any time files, templates, or the date/partner-ID inputs change:

1. `compareHeaders` — normalizes (via `normalizeHeader`, which strips newlines/BOM/zero-width chars and unifies smart quotes) and diffs actual vs. expected headers position-by-position for both Row 1 and Row 3, per file.
2. Checks that at least one non-empty shop data row exists from Row 4 onward.
3. `generateOutputText` — builds the pipe-delimited output: one header line (from Row 2 of the first valid file, column count = `templateRow1.length`) followed by one line per shop record across all valid files (column count = `templateRow3.length`). `cleanCellValue` strips single quotes from every cell (`'` is not allowed in the output format).
4. `runOutputVerification` — re-scans the *generated* output text line-by-line for leftover single quotes and for pipe-count mismatches against the expected column counts, producing `state.outputIssues`. This runs automatically after every conversion, not as a separate manual step.
5. `updateOverallStatus` gates the Export button: it stays disabled if any file has `status === 'error'` or any output issues were found.

Template Settings tab (`initSettingsPanel`) lets a user override `templateRow1`/`templateRow3` either by typing comma/newline-separated column names, or by uploading a reference Excel file (`handleTemplateExcelFile`) whose Row 1 and Row 3 are extracted verbatim as the new templates. Changing templates re-runs `processUploadedFiles` on any already-uploaded files.

### Export

`exportTextFile` downloads `state.outputText` as `register_qrapiv2_{partnerId}_{yyyyMMdd}.txt` via a Blob + temporary `<a download>`, using the current Partner ID input and File Date input to build the filename.
