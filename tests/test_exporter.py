from backend.exporter import _sanitize_latex, export_pdf, export_txt

FULL_REPORT = """# Quantum Computing in 2025

## Overview
Quantum computers use **qubits** [1]. Inline math `O(n log n)` and a link
[IBM](https://ibm.com/quantum).

## Key Findings
- Error rates fell — “significantly” [2]
- See [the paper](https://arxiv.org/abs/1)

```
(x + y)^n = Sum(k=0 to n) C(n,k) * x^(n-k) * y^k
```

| Company | Qubits |
|---|---|
| IBM | 1121 |

> A quoted line.

---

## Sources

1. [Quantum page](https://example.com/q) — Web
2. [A paper](https://arxiv.org/abs/1) — A, B, arXiv, 2024
"""


def test_export_pdf_full_report():
    data = export_pdf(FULL_REPORT, "quantum")
    assert data.startswith(b"%PDF")
    assert len(data) > 1000


def test_export_pdf_without_headings_uses_filename():
    assert export_pdf("Just one line of text.", "plain_title").startswith(b"%PDF")


def test_export_pdf_handles_non_latin_text():
    assert export_pdf("# 量子 计算\n\nEmoji 🚀 and Greek αβγ", "x").startswith(b"%PDF")


def test_export_txt_is_utf8():
    assert export_txt("héllo", "x") == "héllo".encode()


def test_sanitize_latex():
    assert _sanitize_latex(r"\frac{a}{b}") == "(a)/(b)"
    assert _sanitize_latex(r"\binom{n}{k}") == "C(n, k)"
    assert _sanitize_latex(r"x^{n-k}") == "x^(n-k)"
