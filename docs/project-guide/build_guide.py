"""Bundle a local teaching site. Read only an explicit safe code allowlist."""

from __future__ import annotations

import ast
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ALLOWED = [
    "main.py", "tools.py", "scientific_tools.py", "research_models.py", "budget.py", "safety.py", "tracing.py",
    "scripts/check_scientific_sources.py", "scripts/export_trace.py",
    "tests/test_task2.py", "tests/test_scientific.py", "tests/test_tracing_budget.py",
]


def source_index() -> dict:
    index = {}
    for relative in ALLOWED:
        source = (ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        nodes = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nodes.append({"name": node.name, "qualified": node.name, "line": node.lineno,
                              "kind": "class" if isinstance(node, ast.ClassDef) else "function"})
                if isinstance(node, ast.ClassDef):
                    for member in node.body:
                        if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            nodes.append({"name": member.name, "qualified": node.name + "." + member.name,
                                          "line": member.lineno, "kind": "function"})
        index[relative] = {"text": source, "lines": len(source.splitlines()), "nodes": nodes}
    return index


def main() -> None:
    data = json.dumps(source_index(), ensure_ascii=False).replace("</", "<\\/")
    css = (HERE / "style.css").read_text(encoding="utf-8")
    content = (HERE / "content.js").read_text(encoding="utf-8")
    functions = (HERE / "functions.js").read_text(encoding="utf-8")
    app = (HERE / "app.js").read_text(encoding="utf-8")
    html = """<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'">
<meta name="description" content="دليل عربي مبسط لفهم مشروع المساعد البحثي، ملفا بملف، مع أمثلة تفاعلية دون استدعاء النموذج.">
<title>افهم مشروعك — دليل المساعد البحثي</title><style>__CSS__</style></head><body>
<a href="#home" class="sr-only">الانتقال إلى الدليل</a>
<div class="layout"><aside class="sidebar" id="sidebar" aria-label="فهرس الدليل">
<div class="brand"><div class="brand-line"><div class="brand-icon" aria-hidden="true">م</div><div><strong>افهم مشروعك</strong><div class="subtitle">AI RESEARCH ASSISTANT · دليل الكود</div></div></div></div>
<div class="searchbox"><label class="sr-only" for="nav-search">ابحث عن ملف أو وظيفة</label><input id="nav-search" placeholder="ابحث عن ملف أو وظيفة… Ctrl K" autocomplete="off" type="search"></div>
<nav class="nav" id="nav" aria-label="صفحات الدليل"></nav>
<div class="sidebar-foot"><strong>خطوة صغيرة، فهم أوضح.</strong><div id="progress-label"></div><div class="progress-track"><div class="progress-fill" id="progress-fill"></div></div></div>
</aside><div id="overlay" class="overlay"></div><div class="main-shell">
<header class="topbar"><div class="top-actions"><button class="mini menu-button" id="menu-toggle" aria-expanded="false" aria-controls="sidebar">☰ الفهرس</button><span class="breadcrumb" id="breadcrumb"></span></div><div class="top-actions"><span class="pill">دليل محلي · بلا رصيد API</span><button id="print-page" title="طباعة الصفحة الحالية">طباعة الصفحة</button></div></header>
<main class="article" id="article" tabindex="-1"></main><footer class="footer"><span>شرح مبني على الكود حتى المهمتين 3 و4 · 4 نوفمبر 2026</span><span>أمثلة تعليمية · لا أسرار ولا طلبات نموذج</span></footer>
</div></div><noscript>فعّل JavaScript للتنقل داخل الدليل التعليمي المحلي.</noscript>
<script>window.SOURCE_INDEX=__DATA__;
__CONTENT__
__FUNCTIONS__
__APP__</script></body></html>"""
    for marker, value in [("__CSS__", css), ("__DATA__", data), ("__CONTENT__", content),
                          ("__FUNCTIONS__", functions), ("__APP__", app)]:
        html = html.replace(marker, value)
    output = HERE / "index.html"
    output.write_text(html, encoding="utf-8", newline="\n")
    print("Built local guide:", output)
    print("Bytes:", output.stat().st_size)


if __name__ == "__main__":
    main()
