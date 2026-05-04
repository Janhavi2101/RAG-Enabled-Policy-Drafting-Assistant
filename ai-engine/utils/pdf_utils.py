from pathlib import Path


def _get_pdf_reader():
    try:
        from pypdf import PdfReader  # type: ignore

        return PdfReader
    except ImportError:
        pass

    try:
        from PyPDF2 import PdfReader  # type: ignore

        return PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "PDF extraction dependency not installed. Install 'pypdf' or 'PyPDF2'."
        ) from exc


def extract_text_from_pdf(pdf_path):
    PdfReader = _get_pdf_reader()
    reader = PdfReader(str(Path(pdf_path)))
    pages = []

    for page in reader.pages:
        page_text = page.extract_text() or ""
        lines = []
        for raw_line in page_text.splitlines():
            normalized_line = " ".join(raw_line.split())
            if normalized_line:
                lines.append(normalized_line)
        if lines:
            pages.append("\n".join(lines))

    return "\n\n".join(pages).strip()
