"""
Export module — generates downloadable .txt and .pdf files from research content.
Uses fpdf2 for PDF generation with proper page layout and Unicode handling.
All files written to the configured output directory.
"""

from __future__ import annotations

import os
import re
from typing import Any

from fpdf import FPDF

from backend.config import settings
from backend.errors import ExportError
from backend.utils import logger

# Resolve output directory to absolute path at import time
OUTPUT_DIR: str = os.path.abspath(settings.output_dir)


def _sanitize_filename(filename: str) -> str:
    """Strip special characters from filename to prevent path traversal."""
    sanitized: str = re.sub(r"[^\w\s-]", "", filename.strip())
    sanitized = re.sub(r"\s+", "_", sanitized)
    return sanitized[:80] if sanitized else "research_output"


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
        "\u2013": "-", "\u2014": "--",
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
    # Remove any remaining non-latin1 characters rather than replacing with '?'
    return text.encode("latin-1", errors="ignore").decode("latin-1")


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


def export_txt(content: str, filename: str) -> str:
    """
    Save content as a .txt file and return the absolute file path.

    Args:
        content: The raw research content to save.
        filename: The base filename (sanitized internally).

    Returns:
        Absolute path to the generated .txt file.
    """
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        safe_filename: str = _sanitize_filename(filename)
        path: str = os.path.join(OUTPUT_DIR, f"{safe_filename}.txt")

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Exported .txt to: {path}")
        return path

    except Exception as e:
        logger.error(f"TXT export failed: {e}")
        raise ExportError(f"Failed to export .txt: {str(e)}")


def export_pdf(content: str, filename: str) -> str:
    """
    Save content as a professionally formatted .pdf file.

    Parses markdown-style content and renders with proper typography:
    - Clean title page with topic name
    - Section headers with visual separators
    - Bullet points with indentation
    - URLs in blue
    - Proper text wrapping and page breaks

    Args:
        content: The raw research content (may contain markdown).
        filename: The base filename (sanitized internally).

    Returns:
        Absolute path to the generated .pdf file.
    """
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        safe_filename: str = _sanitize_filename(filename)
        path: str = os.path.join(OUTPUT_DIR, f"{safe_filename}.pdf")

        pdf = FPDF(orientation="P", unit="mm", format="A4")
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
        for cline in content.split("\n"):
            cline_s = cline.strip()
            # Use a top-level heading (#) as the title if one exists
            m_title = re.match(r'^#\s+(.+)$', cline_s)
            if m_title:
                title_text = m_title.group(1)
                break
            # Otherwise grab the first ## heading text as the title
            m_h2 = re.match(r'^##\s+(.+)$', cline_s)
            if m_h2 and not title_text:
                title_text = m_h2.group(1)
                # Don't break — keep looking for a better # heading
        # Fallback: use the filename if no heading found in content
        if not title_text or title_text.lower() in ('overview', 'key findings', 'sources', 'important details'):
            title_text = filename.replace("_", " ")

        clean_title: str = _clean_text(_strip_markdown(title_text))

        # ---- Styled Title Block ----
        pdf.set_fill_color(30, 64, 136)  # Deep blue banner
        pdf.rect(0, 0, 210, 32, style='F')
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(255, 255, 255)  # White on blue
        pdf.set_y(8)
        pdf.multi_cell(w=0, h=8, text=clean_title, align="C")
        pdf.set_y(35)

        # Thin accent line
        pdf.set_draw_color(70, 130, 180)
        pdf.set_line_width(0.6)
        pdf.line(left, pdf.get_y(), left + usable_w, pdf.get_y())
        pdf.ln(6)

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

        for line in content.split("\n"):
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
                pdf.multi_cell(w=usable_w, h=7, text=clean)
                pdf.set_text_color(40, 40, 50)  # Reset
                pdf.set_font("Helvetica", size=10)
                pdf.ln(2)
                continue

            m_h2 = re.match(r"^#{2}\s*(.+)$", stripped)
            if m_h2:
                clean = _clean_text(_strip_markdown(m_h2.group(1)))
                pdf.ln(7)
                pdf.set_fill_color(240, 245, 255)  # Very light blue background
                pdf.set_text_color(30, 64, 136)  # Deep blue
                pdf.set_font("Helvetica", "B", 13)
                pdf.set_x(left)
                pdf.multi_cell(w=usable_w, h=9, text=f"  {clean}", fill=True)
                pdf.set_text_color(40, 40, 50)  # Reset
                pdf.set_font("Helvetica", size=10)
                pdf.ln(3)
                continue

            m_h1 = re.match(r"^#\s*(.+)$", stripped)
            if m_h1:
                clean = _clean_text(_strip_markdown(m_h1.group(1)))
                pdf.ln(9)
                pdf.set_fill_color(30, 64, 136)  # Deep blue background
                pdf.set_text_color(255, 255, 255)  # White text
                pdf.set_font("Helvetica", "B", 14)
                pdf.set_x(left)
                pdf.multi_cell(w=usable_w, h=10, text=f"  {clean}", fill=True)
                pdf.set_text_color(40, 40, 50)  # Reset
                pdf.set_font("Helvetica", size=10)
                pdf.ln(4)
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
                            pdf.write(6, _clean_text(before))
                        pdf.set_font("Helvetica", "U", 10)
                        pdf.set_text_color(50, 80, 180)
                        pdf.write(6, _clean_text(lm.group(1)), lm.group(2))
                        last_end = lm.end()
                    after = bullet_content[last_end:]
                    if after:
                        pdf.set_font("Helvetica", size=10)
                        pdf.set_text_color(40, 40, 50)
                        pdf.write(6, _clean_text(after))
                    pdf.ln(7)
                    pdf.set_text_color(40, 40, 50)
                else:
                    clean = _clean_text(bullet_content)
                    pdf.set_font("Helvetica", size=10)
                    pdf.set_x(left + 8)
                    pdf.multi_cell(w=usable_w - 12, h=6, text=f"-  {clean}", markdown=True, align="L")
                pdf.ln(1.5)
                continue

            # Numbered list items — use wider indent
            m_num = re.match(r"^(\d+)\.\s+(.+)$", stripped)
            if m_num:
                num: str = m_num.group(1)
                item_text: str = _clean_text(m_num.group(2))
                pdf.set_font("Helvetica", size=10)
                pdf.set_x(left + 8)
                pdf.multi_cell(w=usable_w - 12, h=6, text=f"{num}. {item_text}", markdown=True, align="L")
                pdf.ln(1.5)
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

            # Regular paragraph text — check for inline links first
            link_matches = list(re.finditer(r'\[([^\]]+)\]\((https?://[^)]+)\)', stripped))
            if link_matches:
                # Render paragraph with clickable links
                last_end = 0
                for lm in link_matches:
                    before = stripped[last_end:lm.start()]
                    if before:
                        clean_before = _clean_text(before)
                        pdf.set_font("Helvetica", size=10)
                        pdf.set_text_color(40, 40, 50)
                        pdf.write(6, clean_before)
                    link_text = _clean_text(lm.group(1))
                    link_url = lm.group(2)
                    pdf.set_font("Helvetica", "U", 10)
                    pdf.set_text_color(50, 80, 180)
                    pdf.write(6, link_text, link_url)
                    last_end = lm.end()
                after = stripped[last_end:]
                if after:
                    clean_after = _clean_text(after)
                    pdf.set_font("Helvetica", size=10)
                    pdf.set_text_color(40, 40, 50)
                    pdf.write(6, clean_after)
                pdf.ln(7)
                pdf.set_text_color(40, 40, 50)
                pdf.set_font("Helvetica", size=10)
            else:
                clean = _clean_text(stripped)
                pdf.set_font("Helvetica", size=10)
                pdf.set_text_color(40, 40, 50)
                pdf.set_x(left)
                pdf.multi_cell(w=usable_w, h=6, text=clean, markdown=True, align="L")
            pdf.ln(2)

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

        pdf.output(path)
        logger.info(f"Exported .pdf to: {path}")
        return path

    except Exception as e:
        logger.error(f"PDF export failed: {e}")
        raise ExportError(f"Failed to export .pdf: {str(e)}")
