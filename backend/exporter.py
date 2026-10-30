"""
Export module — generates downloadable .txt and .pdf files from research content.
Uses fpdf2 for PDF generation with proper page layout and Unicode handling.
Files are built in memory and returned as bytes — nothing is written to disk,
so concurrent exports can never overwrite each other (and it works on
read-only filesystems such as Vercel).
"""

from __future__ import annotations

import re
from datetime import date

from fpdf import FPDF

from backend.errors import ExportError
from backend.utils import logger


def _sanitize_latex(text: str) -> str:
    """Convert raw LaTeX math into clean plaintext before PDF processing."""
    # Strip MathJax block/inline delimiters
    text = re.sub(r'\\\[|\\\]|\\\(|\\\)', '', text)
    text = re.sub(r'\$\$?', '', text)

    # --- Multi-argument LaTeX functions (handle nested braces) ---
    # \binom{n}{k} → C(n, k)
    text = re.sub(r'\\binom\{([^}]*)\}\{([^}]*)\}', r'C(\1, \2)', text)
    # \frac{a}{b} → (a)/(b)
    text = re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'(\1)/(\2)', text)
    # \sqrt{x} → sqrt(x)
    text = re.sub(r'\\sqrt\{([^}]*)\}', r'sqrt(\1)', text)

    # --- Sum/Product with limits ---
    # \sum_{a}^{b} → Sum(a to b)
    text = re.sub(r'\\sum_\{([^}]*)\}\^\{([^}]*)\}', r'Sum(\1 to \2)', text)
    # \sum_{a} → Sum(a)
    text = re.sub(r'\\sum_\{([^}]*)\}', r'Sum(\1)', text)
    # \sum → Sum
    text = text.replace('\\sum', 'Sum')
    # \prod_{a}^{b} → Product(a to b)
    text = re.sub(r'\\prod_\{([^}]*)\}\^\{([^}]*)\}', r'Product(\1 to \2)', text)
    text = re.sub(r'\\prod_\{([^}]*)\}', r'Product(\1)', text)
    # \log_{b} → log_b
    text = re.sub(r'\\log_\{([^}]*)\}', r'log_\1', text)
    # \text{...} → just the text
    text = re.sub(r'\\text\{([^}]*)\}', r'\1', text)
    # \sim → ~
    text = text.replace('\\sim', '~')

    # --- Named LaTeX symbols → plaintext ---
    latex_symbols = {
        '\\displaystyle': '', '\\quad': ' ', '\\qquad': '  ',
        '\\dots': '...', '\\ldots': '...', '\\cdots': '...',
        '\\cdot': '*', '\\times': 'x',
        '\\le': '<=', '\\leq': '<=', '\\ge': '>=', '\\geq': '>=',
        '\\neq': '!=', '\\ne': '!=', '\\approx': '~=',
        '\\infty': 'inf', '\\pi': 'pi',
        '\\Theta': 'Theta', '\\theta': 'theta',
        '\\Omega': 'Omega', '\\omega': 'omega',
        '\\alpha': 'alpha', '\\beta': 'beta', '\\gamma': 'gamma',
        '\\delta': 'delta', '\\epsilon': 'epsilon', '\\lambda': 'lambda',
        '\\mu': 'mu', '\\sigma': 'sigma', '\\phi': 'phi',
        '\\left': '', '\\right': '', '\\,': ' ', '\\;': ' ', '\\!': '',
        '\\lfloor': 'floor(', '\\rfloor': ')', '\\lceil': 'ceil(', '\\rceil': ')',
        '\\lim': 'lim', '\\max': 'max', '\\min': 'min', '\\log': 'log',
        '\\ln': 'ln', '\\sin': 'sin', '\\cos': 'cos', '\\tan': 'tan',
    }
    for k, v in latex_symbols.items():
        text = text.replace(k, v)

    # --- Superscript/subscript brace cleanup ---
    # x^{n-k} → x^(n-k)  and  x^{n} → x^n
    def _clean_brace_group(match):
        prefix = match.group(1)  # ^ or _
        content = match.group(2)
        if len(content) <= 1:
            return f"{prefix}{content}"  # x^n (no parens needed)
        return f"{prefix}({content})"     # x^(n-k)
    text = re.sub(r'(\^)\{([^}]*)\}', _clean_brace_group, text)
    text = re.sub(r'(_)\{([^}]*)\}', _clean_brace_group, text)

    # --- Catch any remaining \command patterns and strip the backslash ---
    text = re.sub(r'\\([a-zA-Z]+)', r'\1', text)

    # --- Clean up stray braces and extra whitespace ---
    text = text.replace('{', '').replace('}', '')
    text = re.sub(r' {2,}', ' ', text).strip()

    return text


def _clean_text(text: str) -> str:
    """
    Clean text for PDF — replace Unicode characters and sanitize LaTeX.
    """
    text = _sanitize_latex(text)

    replacements: dict[str, str] = {
        "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"',
        "\u2013": " - ", "\u2014": " -- ",
        "\u2026": "...",
        "\u2022": "-",
        "\u00b7": "-",
        "\u2023": ">",
        "\u00a0": " ",
        "\u200b": "",
        "\u2010": "-", "\u2011": "-", "\u2012": "-",
        "\u00d7": "x",
        "\u2192": "->", "\u2190": "<-", "\u2194": "<->",
        "\u2713": "[Y]", "\u2717": "[X]",
        "\u00ae": "(R)", "\u2122": "(TM)", "\u00a9": "(c)",
        "\u00b2": "2", "\u00b3": "3", "\u00b9": "1",
        "\u2070": "0", "\u2074": "4", "\u2075": "5",
        "\u207b": "-", "\u207a": "+",
        "\u22c5": "*", "\u2211": "Sum ", "\u220f": "Product ",
        "\u221a": "sqrt", "\u221e": "infinity", "\u2248": "~=",
        "\u2260": "!=", "\u2264": "<=", "\u2265": ">=",
        "\u03b8": "Theta", "\u0398": "Theta", "\u03a9": "Omega",
        "\u03c9": "omega", "\u039f": "O", "\u03bf": "o",
        "\u03b1": "alpha", "\u03b2": "beta", "\u03b3": "gamma",
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)

    # Replace non-latin1 characters with space to prevent word joining
    # This fixes issues like 'mechanicssuperposition'
    cleaned = []
    for ch in text:
        try:
            ch.encode("latin-1")
            cleaned.append(ch)
        except UnicodeEncodeError:
            cleaned.append(" ")
    text = "".join(cleaned)
    return re.sub(r' {2,}', ' ', text).strip()


def _clean_fragment(text: str) -> str:
    """Like _clean_text, but keeps one leading/trailing space (text next to a link)."""
    lead = " " if text[:1].isspace() else ""
    trail = " " if text[-1:].isspace() else ""
    return lead + _clean_text(_strip_markdown(text)) + trail


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting characters for clean PDF text."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # Bold
    text = re.sub(r"\*(.+?)\*", r"\1", text)       # Italic
    text = re.sub(r"__(.+?)__", r"\1", text)        # Bold
    text = re.sub(r"_(.+?)_", r"\1", text)          # Italic
    text = re.sub(r"`(.+?)`", r"\1", text)          # Code
    # Keep link text but preserve URL for PDF link rendering
    # [text](url) → text (url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    return text


def _generated_line() -> str:
    return f"Generated by AI Research Assistant on {date.today():%d %B %Y}"


def markdown_to_text(content: str) -> str:
    """
    Convert the markdown summary into readable plain text:
    underlined headings, "text (url)" links and no formatting markers.
    """
    out: list[str] = []
    in_code = False
    for line in content.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            out.append("    " + line)
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            text = _inline_to_text(heading.group(2))
            level = len(heading.group(1))
            if out and out[-1] != "":
                out.append("")
            out.append(text.upper() if level == 1 else text)
            if level <= 2:
                out.append(("=" if level == 1 else "-") * len(text))
            continue
        if re.match(r"^\|[\s\-:|]+\|$", stripped):   # table separator row
            continue
        out.append(_inline_to_text(line.rstrip()))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def _inline_to_text(text: str) -> str:
    def link(m: re.Match[str]) -> str:
        label, url = m.group(1), m.group(2)
        return url if label.strip() == url.strip() else f"{label} ({url})"

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", text)
    return text.replace("`", "")


def export_txt(content: str, filename: str) -> bytes:
    """
    Build a plain-text .txt file (markdown converted to readable text).

    Args:
        content: The raw research content (markdown).
        filename: Unused; kept for a signature symmetric with export_pdf.

    Returns:
        The file contents as UTF-8 bytes.
    """
    try:
        return (markdown_to_text(content) + "\n" + _generated_line() + "\n").encode("utf-8")
    except Exception as e:
        logger.error(f"TXT export failed: {e}")
        raise ExportError(f"Failed to export .txt: {e}") from e


def export_md(content: str, filename: str) -> bytes:
    """Build a Markdown file: the summary as-is plus a generated-by line."""
    try:
        return (content.rstrip() + f"\n\n---\n\n*{_generated_line()}*\n").encode("utf-8")
    except Exception as e:
        logger.error(f"MD export failed: {e}")
        raise ExportError(f"Failed to export .md: {e}") from e


class _ReportPDF(FPDF):
    """FPDF with a "Page X of Y" footer on every page."""

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(140, 140, 160)
        self.cell(0, 10, f"Page {self.page_no()} of {{nb}}", align="C")


def export_pdf(content: str, filename: str) -> bytes:
    """
    Build a professionally formatted .pdf from the research content.

    Parses markdown-style content and renders with proper typography:
    - Clean title page with topic name
    - Section headers with visual separators
    - Bullet points with indentation
    - URLs in blue
    - Proper text wrapping and page breaks

    Args:
        content: The raw research content (may contain markdown).
        filename: Used as the PDF title when the content has no heading.

    Returns:
        The PDF file contents as bytes.
    """
    def render_text_with_code(pdf, text, current_x=None, line_height=6):
        if current_x is not None:
            pdf.set_x(current_x)

        base_style = pdf.font_style
        # Split out inline code and **bold** spans first
        parts = re.split(r'(`[^`]+`|\*\*[^*]+\*\*)', text)
        for part in parts:
            if part.startswith("`") and part.endswith("`") and len(part) > 1:
                pdf.set_font("Courier", "B", pdf.font_size_pt)
                pdf.write(line_height, part[1:-1])
                pdf.set_font("Helvetica", base_style, pdf.font_size_pt)
            elif part.startswith("**") and part.endswith("**") and len(part) > 4:
                pdf.set_font("Helvetica", "B" + base_style.replace("B", ""), pdf.font_size_pt)
                pdf.write(line_height, part[2:-2])
                pdf.set_font("Helvetica", base_style, pdf.font_size_pt)
            else:
                # In non-code parts, look for links: [text](url)
                # Enhanced regex to be more robust with parentheses in URLs
                sub_parts = re.split(r'(\[[^\]]+\]\(https?://[^\s\)]+\))', part)
                for sub in sub_parts:
                    m_link = re.match(r'\[([^\]]+)\]\((https?://[^\s\)]+)\)', sub)
                    if m_link:
                        link_text = m_link.group(1)
                        link_url = m_link.group(2)

                        pdf.set_text_color(50, 80, 180) # Link blue
                        pdf.set_font("Helvetica", "U", pdf.font_size_pt)

                        # If link text is different from URL, show both for clarity
                        display_text = link_text
                        if link_text.strip() != link_url.strip() and not link_url.endswith(link_text):
                            display_text = f"{link_text} ({link_url})"

                        pdf.write(line_height, display_text, link_url)
                        pdf.set_text_color(40, 40, 50) # Reset
                        pdf.set_font("Helvetica", base_style, pdf.font_size_pt)
                    else:
                        pdf.write(line_height, sub)

    try:
        pdf = _ReportPDF(orientation="P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=25)
        pdf.set_left_margin(25)
        pdf.set_right_margin(25)
        pdf.add_page()

        # Page layout constants
        left: float = pdf.l_margin
        usable_w: float = pdf.w - pdf.l_margin - pdf.r_margin

        # ---- Extract a proper title from the AI content ----
        # Scan content for the first heading or the Overview paragraph
        title_text: str = ""
        title_line_index: int = -1
        lines = content.split("\n")
        for idx, cline in enumerate(lines):
            cline_s = cline.strip()
            # Use a top-level heading (#) as the title if one exists
            m_title = re.match(r'^#\s+(.+)$', cline_s)
            if m_title:
                title_text = m_title.group(1)
                title_line_index = idx
                break
            # Otherwise grab the first ## heading text as the title
            m_h2 = re.match(r'^##\s+(.+)$', cline_s)
            if m_h2 and not title_text:
                title_text = m_h2.group(1)
        # Don't break — keep looking for a better # heading
        # If no heading found, use the first non-empty line as a candidate
        if not title_text:
            for cline in content.split("\n"):
                if cline.strip() and not cline.strip().startswith("|"):
                    title_text = cline.strip()[:60] # Truncate for "short" title
                    break
        # Fallback: use the filename if no heading found in content
        if not title_text or title_text.lower() in ('overview', 'key findings', 'sources', 'important details', 'related research papers'):
            title_text = filename.replace("_", " ")

        # ---- Styled Title Block ----
        # Use a more sophisticated Title Case that doesn't capitalize small words
        def proper_title_case(s):
            small_words = {'a', 'an', 'the', 'and', 'but', 'or', 'for', 'nor', 'on', 'at', 'to', 'from', 'by', 'with', 'in', 'of'}
            words = s.split()
            if not words:
                return ""
            result = [words[0].capitalize()]
            for word in words[1:]:
                result.append(word.lower() if word.lower() in small_words else word.capitalize())
            return " ".join(result)

        clean_title: str = proper_title_case(_clean_text(_strip_markdown(title_text)))

        pdf.set_fill_color(30, 64, 136)  # Deep blue banner
        pdf.rect(0, 0, 210, 32, style='F')
        pdf.set_font("Helvetica", "B", 18)
        pdf.set_text_color(255, 255, 255)  # White on blue
        pdf.set_y(10)
        pdf.multi_cell(w=0, h=10, text=clean_title, align="C")
        pdf.set_y(36)

        # Generated date, right-aligned above the accent line
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(120, 120, 140)
        pdf.cell(w=usable_w, h=5, text=f"Generated on {date.today():%d %B %Y}", align="R")
        pdf.ln(7)

        # Thin accent line with more gap
        pdf.set_draw_color(70, 130, 180)
        pdf.set_line_width(0.6)
        pdf.line(left, pdf.get_y(), left + usable_w, pdf.get_y())
        pdf.ln(10) # Even more gap before text starts

        # ---- Process content line by line ----
        pdf.set_text_color(30, 30, 40)

        table_buffer: list[list[str]] = []

        def flush_table():
            if not table_buffer:
                return
            # Render the buffered table cells using fpdf2 native table handling
            pdf.set_font("Helvetica", size=9)
            with pdf.table(borders_layout="ALL", text_align="LEFT", cell_fill_color=245) as table:
                for row_idx, row_cells in enumerate(table_buffer):
                    row = table.row()
                    for cell in row_cells:
                        # Make header row bold and deep blue
                        if row_idx == 0:
                            pdf.set_font("Helvetica", "B", 9)
                            pdf.set_text_color(30, 64, 136)
                        else:
                            pdf.set_font("Helvetica", size=9)
                            pdf.set_text_color(30, 30, 40)
                        row.cell(cell)
            pdf.ln(4)
            pdf.set_text_color(30, 30, 40) # Ensure reset after table
            table_buffer.clear()

        in_code_block: bool = False
        code_block_lines: list[str] = []

        for i, line in enumerate(content.split("\n")):
            stripped: str = line.strip()

            # ---- Code block detection (``` ... ```) ----
            if stripped.startswith("```"):
                if in_code_block:
                    # End of code block — render it
                    in_code_block = False
                    code_text = "\n".join(code_block_lines)
                    clean_code = _clean_text(code_text)
                    pdf.set_fill_color(240, 242, 245)  # Light grey background
                    pdf.set_font("Courier", size=9)
                    pdf.set_text_color(40, 40, 50)
                    pdf.set_x(left + 4)
                    pdf.multi_cell(w=usable_w - 8, h=5, text=clean_code, fill=True, align="L")
                    pdf.set_font("Helvetica", size=10)
                    pdf.ln(3)
                    code_block_lines = []
                else:
                    in_code_block = True
                    code_block_lines = []
                continue
            if in_code_block:
                code_block_lines.append(line)
                continue

            # Table rows (| ... | ... |)
            if stripped.startswith("|") and stripped.endswith("|"):
                # Skip markdown separator rows
                if re.match(r"^\|[\s\-:|]+\|$", stripped):
                    continue
                cells = [_clean_text(_strip_markdown(c.strip())) for c in stripped.split("|") if c.strip()]
                if cells:
                    table_buffer.append(cells)
                continue
            else:
                flush_table()

            if not stripped:
                pdf.ln(4)
                continue

            # ---- Math formula detection ----
            # Lines that look like standalone math: contain ^, =, Sum(, C(, etc.
            # but are NOT headers, bullets, or regular prose (short + math-heavy)
            is_math = (
                not stripped.startswith("#") and
                not stripped.startswith("-") and
                not stripped.startswith(">") and
                len(stripped) < 200 and
                re.search(r'[\^=]', stripped) and
                re.search(r'(?:\b(?:Sum|C|T|O|P|log|sqrt)\s*\(|[\^_]\(|\^[0-9]|\bfor\b.*\b[kn]\b)', stripped)
            )
            if is_math:
                clean_math = _clean_text(stripped)
                pdf.set_fill_color(240, 242, 245)  # Light grey background
                pdf.set_font("Courier", size=9)
                pdf.set_text_color(40, 40, 50)
                pdf.set_x(left + 4)
                pdf.multi_cell(w=usable_w - 8, h=6, text=f"  {clean_math}", fill=True, align="L")
                pdf.set_font("Helvetica", size=10)
                pdf.ln(2)
                continue

            # Remove markdown header markers
            m_h3 = re.match(r"^#{3}\s*(.+)$", stripped)
            if m_h3:
                clean: str = _clean_text(_strip_markdown(m_h3.group(1)))
                pdf.ln(5)
                pdf.set_text_color(70, 130, 180)  # Steel blue
                pdf.set_font("Helvetica", "B", 11)
                pdf.set_x(left)
                render_text_with_code(pdf, clean)
                pdf.set_text_color(40, 40, 50)  # Reset
                pdf.set_font("Helvetica", size=10)
                pdf.ln(5)
                continue

            m_h2 = re.match(r"^#{2}\s*(.+)$", stripped)
            if m_h2:
                clean = _clean_text(_strip_markdown(m_h2.group(1)))
                pdf.ln(8) # Increased gap
                pdf.set_fill_color(240, 245, 255)  # Very light blue background
                pdf.set_text_color(30, 64, 136)  # Deep blue
                pdf.set_font("Helvetica", "B", 13)
                pdf.set_x(left)
                pdf.cell(w=usable_w, h=9, text="", fill=True) # Draw background
                pdf.set_x(left + 2)
                render_text_with_code(pdf, clean)
                pdf.set_text_color(40, 40, 50)  # Reset
                pdf.set_font("Helvetica", size=10)
                pdf.ln(6)
                continue

            m_h1 = re.match(r"^#\s*(.+)$", stripped)
            if m_h1:
                # Skip if this was the line used for the banner title
                if i == title_line_index:
                    continue
                clean = _clean_text(_strip_markdown(m_h1.group(1)))
                pdf.ln(9)
                pdf.set_fill_color(30, 64, 136)  # Deep blue background
                pdf.set_text_color(255, 255, 255)  # White text
                pdf.set_font("Helvetica", "B", 14)
                pdf.set_x(left)
                pdf.cell(w=usable_w, h=10, text="", fill=True) # Draw background
                pdf.set_x(left + 2)
                render_text_with_code(pdf, clean)
                pdf.set_text_color(40, 40, 50)  # Reset
                pdf.set_font("Helvetica", size=10)
                pdf.ln(6)
                continue

            # Horizontal rule
            if re.match(r"^-{3,}$", stripped) or re.match(r"^\*{3,}$", stripped):
                pdf.set_draw_color(200, 200, 210)
                pdf.set_line_width(0.2)
                pdf.line(left, pdf.get_y(), left + usable_w, pdf.get_y())
                pdf.ln(4)
                continue

            # Bullet / list items — use wider indent to prevent corner overflow
            if re.match(r"^[-*\u2022]\s+", stripped):
                bullet_content: str = re.sub(r"^[-*\u2022]\s+", "", stripped)

                # Check for inline links in bullet
                link_matches = list(re.finditer(r'\[([^\]]+)\]\((https?://[^)]+)\)', bullet_content))
                if link_matches:
                    pdf.set_font("Helvetica", size=10)
                    pdf.set_x(left + 8)
                    pdf.set_text_color(30, 64, 136)
                    pdf.write(6, "-  ")
                    pdf.set_text_color(40, 40, 50)
                    last_end = 0
                    for lm in link_matches:
                        before = bullet_content[last_end:lm.start()]
                        if before:
                            pdf.set_font("Helvetica", size=10)
                            pdf.set_text_color(40, 40, 50)
                            pdf.write(6, _clean_fragment(before))
                        pdf.set_font("Helvetica", "U", 10)
                        pdf.set_text_color(50, 80, 180)
                        pdf.write(6, _clean_text(lm.group(1)), lm.group(2))
                        last_end = lm.end()
                    after = bullet_content[last_end:]
                    if after:
                        pdf.set_font("Helvetica", size=10)
                        pdf.set_text_color(40, 40, 50)
                        pdf.write(6, _clean_fragment(after))
                    pdf.ln(7)
                    pdf.set_text_color(40, 40, 50)
                else:
                    clean = _clean_text(bullet_content)
                    pdf.set_font("Helvetica", size=10)
                    pdf.set_x(left + 8)
                    pdf.write(6, "-  ")
                    render_text_with_code(pdf, clean)
                pdf.ln(7)
                continue

            # Numbered list items — use wider indent
            m_num = re.match(r"^(\d+)\.\s+(.+)$", stripped)
            if m_num:
                num: str = m_num.group(1)
                item_text: str = _clean_text(m_num.group(2))
                pdf.set_font("Helvetica", size=10)
                pdf.set_x(left + 8)
                pdf.write(6, f"{num}. ")
                render_text_with_code(pdf, item_text)
                pdf.ln(7.5)
                continue

            # Blockquotes
            m_quote = re.match(r"^>\s*(.+)$", stripped)
            if m_quote:
                clean = _clean_text(m_quote.group(1))
                pdf.set_font("Helvetica", "I", 10)
                pdf.set_text_color(80, 80, 100)
                pdf.set_fill_color(245, 248, 255) # Light blue tint
                pdf.set_x(left + 5)
                pdf.multi_cell(w=usable_w - 10, h=6, text=f"  {clean}", fill=True, markdown=True, align="L")
                pdf.set_text_color(30, 30, 40)
                pdf.set_font("Helvetica", size=10)
                pdf.ln(1)
                continue

            # URLs standing alone
            if stripped.startswith("http://") or stripped.startswith("https://"):
                clean = _clean_text(stripped)
                pdf.set_text_color(50, 80, 180)
                pdf.set_font("Helvetica", size=9)
                pdf.multi_cell(w=usable_w, h=6, text=f"[{clean}]({clean})", markdown=True, align="L")
                pdf.set_text_color(30, 30, 40)
                pdf.set_font("Helvetica", size=10)
                continue

            else:
                clean = _clean_text(stripped)
                render_text_with_code(pdf, clean, current_x=left)
                pdf.ln(7)
            pdf.ln(1)

        flush_table()

        # ---- Footer line on last page ----
        pdf.ln(6)
        pdf.set_draw_color(30, 64, 136)
        pdf.set_line_width(0.3)
        pdf.line(left, pdf.get_y(), left + usable_w, pdf.get_y())
        pdf.ln(3)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(130, 130, 150)
        pdf.multi_cell(w=usable_w, h=5, text="Generated by AI Research Assistant", align="C")

        data: bytes = bytes(pdf.output())
        logger.info(f"Exported .pdf ({len(data)} bytes)")
        return data

    except Exception as e:
        logger.error(f"PDF export failed: {e}")
        raise ExportError(f"Failed to export .pdf: {e}") from e
