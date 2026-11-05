"""Bilingual Streamlit frontend. Research and report state is demo/session-only."""

from __future__ import annotations

import html
from pathlib import Path
import re
import time

import streamlit as st

from frontend.contracts import MODE_LABELS, ResearchRequest, ResearchResult, export_report
from frontend.demo import DemoGateway, DemoResearchError, EXAMPLES, STEPS, localize_result
from frontend.i18n import translate

PAGES = ("مساحة البحث", "التقارير التجريبية", "عن الواجهة")
SCENARIOS = {"عرض مكتمل": "success", "مصدر واحد فقط": "partial", "تعذّر البحث": "error"}


def language():
    return st.session_state.get("ui_language", "ar")


def t(text):
    return translate(text, language())


def toggle_language():
    st.session_state.ui_language = "en" if language() == "ar" else "ar"
    # Selection labels are serialized by Streamlit. Resend their unchanged raw
    # values so the browser checks the newly translated labels immediately.
    for key in ("ui_mode", "ui_page", "ui_scenario", "ui_saved_selection"):
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


def report_text(result):
    return export_report(localize_result(result, language()), language())


def linked_summary(result: ResearchResult) -> str:
    """Link numbered citations to their display references, without raw HTML."""
    def replace(match):
        index = int(match[1])
        return f"[{index}]({result.sources[index - 1].url})" if 1 <= index <= len(result.sources) else match[0]
    return re.sub(r"\[(\d+)\]", replace, result.summary)


def initialize():
    defaults = {"ui_history": [], "ui_saved": [], "ui_active": None, "ui_error": None,
                "ui_preview": True, "ui_query": "", "ui_mode": "web", "ui_page": PAGES[0], "ui_language": "ar"}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def choose_example(mode):
    st.session_state.ui_mode = mode
    st.session_state.ui_query = t(EXAMPLES[mode])
    st.session_state.ui_page = PAGES[0]
    st.session_state.ui_error = None


def open_history(result):
    st.session_state.ui_active = result
    st.session_state.ui_mode = result.request.mode
    st.session_state.ui_query = result.request.query
    st.session_state.ui_preview = False
    st.session_state.ui_error = None
    st.session_state.ui_page = PAGES[0]


def sidebar():
    with st.sidebar:
        st.markdown(t('<div class="brand"><div class="brand-mark">◈</div><div><strong>المساعد البحثي</strong><small>RESEARCH STUDIO</small></div></div>'), unsafe_allow_html=True)
        st.markdown(t('<div class="sidebar-label">مساحة العمل</div>'), unsafe_allow_html=True)
        st.radio(t("التنقل"), PAGES, key="ui_page", label_visibility="collapsed",
                 format_func=lambda value, locale=language(): translate(value, locale))
        st.markdown(t('<div class="sidebar-label">أمثلة للبداية</div>'), unsafe_allow_html=True)
        st.button(t("MCP وربط الأدوات"), key="example_web", on_click=choose_example, args=("web",), width="stretch")
        st.button(t("RAG في التعليم"), key="example_science", on_click=choose_example, args=("scientific",), width="stretch")
        st.divider()
        st.markdown(t('<div class="sidebar-label">سجل جلسة العرض</div>'), unsafe_allow_html=True)
        if not st.session_state.ui_history:
            st.caption(t("لا تجارب بعد. جرّب سؤالًا وسيظهر هنا بعلامة تجريبي."))
        for result in reversed(st.session_state.ui_history[-6:]):
            label = t("تجريبي · ") + result.request.query[:42] + ("…" if len(result.request.query) > 42 else "")
            st.button(label, key="history_" + result.id, on_click=open_history, args=(result,), width="stretch")
        st.markdown(t('<div class="sidebar-note">وضع عرض فقط<br>لا بحث فعلي، لا اتصال بالنموذج، ولا قراءة لسجل أبحاثك الحقيقي.<br><br>تُنسى بيانات الجلسة عند انتهائها. لا تُحفظ في SQLite أو ملفات المشروع.</div>'), unsafe_allow_html=True)


def source_list(result):
    st.caption(t("كل المراجع أدناه أمثلة توضيحية، وليست مصادر مسترجعة أو دراسات منشورة."))
    for index, source in enumerate(result.sources, 1):
        st.markdown(
            t(f'<div class="source-card"><span class="source-number">{index:02}</span><div>'
            f'<a href="{html.escape(source.url, quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(source.title)} ↗</a>'
            f'<p>{html.escape(source.description)}</p><small>EXAMPLE.ORG · مصدر توضيحي</small></div></div>'),
            unsafe_allow_html=True,
        )


def download(result, key):
    st.download_button(t("تنزيل نسخة تجريبية TXT"), data=report_text(result).encode("utf-8"),
        file_name=f"DEMO_{result.request.mode}_{result.id}_{language()}.txt", mime="text/plain; charset=utf-8",
        key=key, width="stretch", icon=":material/download:")


def report_controls(result):
    st.caption(t("الحفظ هنا داخل ذاكرة جلسة العرض فقط، وليس في مجلد reports. التنزيل يحمل علامة DEMO."))
    already_saved = any(item.id == result.id for item in st.session_state.ui_saved)
    accepted = st.checkbox(t("أوافق على الاحتفاظ بهذه النسخة التجريبية داخل الجلسة"), key="consent_" + result.id)
    left, right = st.columns(2)
    with left:
        st.button(t("محفوظ في الجلسة") if already_saved else t("حفظ في جلسة العرض"), key="save_" + result.id,
                  disabled=not accepted or already_saved, width="stretch", icon=":material/bookmark:",
                  on_click=remember_report, args=(result,))
    with right:
        download(result, "download_" + result.id)
    if already_saved:
        st.success(t("نسخة تجريبية محفوظة في الجلسة فقط؛ لم يُنشأ ملف بحث."))


def remember_report(result):
    """Session-only save callback, with an independent consent check."""
    if st.session_state.get("consent_" + result.id, False) and not any(
            item.id == result.id for item in st.session_state.ui_saved):
        st.session_state.ui_saved = (st.session_state.ui_saved + [result])[-20:]


def result_view(result, *, preview=False):
    display = localize_result(result, language())
    state = t("عينة جاهزة") if preview else (t("عرض محدود") if result.status == "partial" else t("اكتمل العرض"))
    st.markdown(
        t(f'<div class="result-top"><div><small>{MODE_LABELS[result.request.mode]} · بيانات تجريبية</small>'
        f'<h2>{html.escape(display.topic)}</h2></div><span class="result-state {"partial" if result.status == "partial" else ""}">{state}</span></div>'),
        unsafe_allow_html=True,
    )
    if preview:
        st.markdown(t('<div class="preview-note">عينة معدّة مسبقًا لتجربة التصميم. لم يبدأ بحث فعلي، ولم تُضف إلى سجل الجلسة.</div>'), unsafe_allow_html=True)
    else:
        st.caption(t("السؤال الذي أدخلته في العرض:"))
        st.write(result.request.query)
        st.info(t("المحتوى التالي عينة ثابتة حسب النمط، وليس إجابة مولّدة عن سؤالك. لم تُستدعَ أي خدمة بحث."), icon=":material/info:")
    if result.status == "partial":
        st.warning(t("حالة تجريبية: مرجع واحد فقط. لا يمكن عرض مقارنة موثقة بين مصدرين."))
    st.markdown(
        t(f'<div class="stats"><div><b>{len(result.sources)}</b><span>مراجع توضيحية</span></div>'
        '<div><b>0</b><span>طلبات API</span></div><div><b>$0</b><span>تكلفة العرض</span></div></div>'), unsafe_allow_html=True,
    )
    summary_tab, sources_tab, tools_tab, report_tab = st.tabs((t("الملخص"), t(f"المصادر ({len(result.sources)})"), t("الأدوات والمسار"), t("التقرير")))
    with summary_tab:
        st.markdown(linked_summary(display))
        st.caption(t("الأرقام داخل النص قابلة للنقر. الروابط مخصصة للعرض فقط."))
    with sources_tab:
        source_list(display)
    with tools_tab:
        st.caption(t("أسماء أدوات ممثّلة في العينة؛ لم تُشغّل أي منها."))
        st.markdown('<div class="tool-chips">' + "".join(f'<span class="tool-chip">{html.escape(tool)}</span>' for tool in result.tools_used) + '</div>', unsafe_allow_html=True)
        for index, step in enumerate(STEPS, 1):
            st.write(f"{index:02} · {t(step.label)}")
        if result.request.mode == "scientific":
            st.caption(t("في الربط القادم: ملخصات وبيانات وصفية فقط، دون أوراق كاملة أو PDF."))
    with report_tab:
        st.text_area(t("معاينة نص التقرير التجريبي"), value=report_text(result), height=220, disabled=True,
                     key="report_text_" + result.id + "_" + language())
        report_controls(result)


def research_page():
    st.markdown(t('<div class="hero"><div class="eyebrow">AI RESEARCH ASSISTANT</div><h1>ابدأ بسؤال.<br><span class="accent">رتّب رحلتك إلى المعرفة.</span></h1><p>مساحة واحدة لبحث الويب ومراجعة الأدبيات العلمية، مع ملخص واضح ومراجع يسهل الرجوع إليها.</p></div>'), unsafe_allow_html=True)
    # Regular widgets commit pending input before the language button reruns.
    with st.container(border=True, key="research_input"):
        st.radio(t("نمط البحث"), ("web", "scientific"),
                 format_func=lambda value, locale=language(): translate(MODE_LABELS[value], locale), key="ui_mode", horizontal=True)
        st.text_area(t("ما الذي تريد استكشافه؟"), key="ui_query", height=110,
            placeholder=t("اكتب سؤالك بالعربية أو الإنجليزية…"), help=t("هذه واجهة تجريبية. سؤالك لا يُرسل إلى نموذج أو محرك بحث."))
        submitted = st.button(t("ابدأ العرض التجريبي"), key="start_demo", type="primary", width="stretch", icon=":material/search:")
    st.markdown(t('<div class="mini-features"><span>◦ مخرجات منظمة</span><span>◦ استشهادات مرقمة</span><span>◦ الحفظ بقرارك</span><span>◦ دون إنفاق في العرض</span></div>'), unsafe_allow_html=True)
    with st.expander(t("جرّب حالات الواجهة"), expanded=False):
        st.caption(t("لتقييم التصميم: بدّل الحالة ثم اضغط «ابدأ العرض التجريبي». لا يُختبر اتصال فعلي."))
        scenario = st.selectbox(t("حالة العرض"), tuple(SCENARIOS), key="ui_scenario",
                               format_func=lambda value, locale=language(): translate(value, locale))
    if submitted:
        try:
            request = ResearchRequest(st.session_state.ui_query, st.session_state.ui_mode)
            st.session_state.ui_error = None
            with st.status(t("تجهيز العرض التجريبي…"), expanded=True) as status:
                progress = st.progress(0, text=t("لا توجد طلبات بحث حقيقية"))

                def on_progress(step):
                    progress.progress(step.fraction, text=t(step.label))
                    time.sleep(0.18)

                try:
                    result = DemoGateway().research(request, on_progress, scenario=SCENARIOS[scenario])
                except DemoResearchError:
                    status.update(label=t("محاكاة تعذّر البحث"), state="error", expanded=True)
                    raise
                status.update(label=t("اكتمل العرض التجريبي دون اتصال خارجي"), state="complete", expanded=False)
            st.session_state.ui_active = result
            st.session_state.ui_preview = False
            st.session_state.ui_history = (st.session_state.ui_history + [result])[-20:]
            st.rerun()
        except (ValueError, DemoResearchError) as error:
            st.session_state.ui_error = str(error)
    if st.session_state.ui_error:
        st.error(t(st.session_state.ui_error))
        st.caption(t("لم تُحفظ نتيجة جديدة. عدّل السؤال أو حالة العرض ثم حاول مجددًا."))
    else:
        st.markdown(t('<div class="section-kicker">مساحة النتائج</div>'), unsafe_allow_html=True)
        result = st.session_state.ui_active
        if result is None:
            result = DemoGateway().research(ResearchRequest(EXAMPLES[st.session_state.ui_mode], st.session_state.ui_mode))
            # Stable preview identity across widget reruns; it is never history.
            preview_key = "ui_sample_" + st.session_state.ui_mode
            if preview_key not in st.session_state:
                st.session_state[preview_key] = result
            result = st.session_state[preview_key]
        with st.container(border=True):
            result_view(result, preview=st.session_state.ui_preview)


def reports_page():
    st.markdown(t('<div class="hero"><div class="eyebrow">DEMO REPORTS</div><h1>تقاريرك في جلسة العرض.</h1><p>نسخ مؤقتة اخترت الاحتفاظ بها. لا تعرض هذه الصفحة ملفات reports أو الأبحاث الحقيقية.</p></div>'), unsafe_allow_html=True)
    saved = st.session_state.ui_saved
    if not saved:
        st.markdown(t('<div class="empty">◇<strong>لم تحفظ نسخة تجريبية بعد</strong>افتح تبويب «التقرير» في أي عينة، وافق على الحفظ، ثم احتفظ بها داخل الجلسة.</div>'), unsafe_allow_html=True)
        st.button(t("العودة إلى مساحة البحث"), on_click=lambda: st.session_state.update(ui_page=PAGES[0]))
        return
    selected = st.selectbox(t("اختر نسخة تجريبية"), range(len(saved)), key="ui_saved_selection",
        format_func=lambda i, locale=language(): f"{translate(MODE_LABELS[saved[i].request.mode], locale)} · {localize_result(saved[i], locale).topic}")
    result = saved[selected]
    st.caption(t("نسخة مؤقتة · DEMO · تختفي عند انتهاء الجلسة"))
    st.text(report_text(result))
    download(result, "library_download_" + result.id)


def about_page():
    st.markdown(t('<div class="hero"><div class="eyebrow">FRONTEND PREVIEW</div><h1>واجهة جاهزة للنقاش.</h1><p>هذه مرحلة مراجعة التصميم والتفاعل، قبل الربط بمحرك البحث.</p></div>'), unsafe_allow_html=True)
    st.info(t("جميع الملخصات والمصادر وحالات التقدم والنتائج هنا تجريبية. لا يوجد مفتاح API أو زر تشغيل حقيقي."))
    st.markdown(t("**ما يمكنك تجربته الآن**\n\nاختيار النمط، كتابة سؤال، عرض النتائج والاستشهادات، تجربة النقص والفشل، الرجوع لسجل الجلسة، والموافقة على حفظ نسخة مؤقتة وتنزيلها."))
    st.markdown(t("**الربط القادم، بعد الموافقة فقط**\n\nتوفير محوّل يطبق `ResearchGateway`، وتحويل روابط المحرك إلى مراجع العرض، وربط التأكيد بخدمة التقارير، ثم ربط السجل بذاكرة SQLite عندما تُنفّذ. لا شيء من ذلك موصول هنا."))
    st.markdown(t("**الخصوصية في هذا العرض**\n\nلا تُقرأ `.env` أو سجلات الإنفاق أو التقارير القديمة. لا تُكتب سجلات بحث JSONL أو قواعد بيانات. النسخ المحفوظة موجودة في ذاكرة جلسة المتصفح، والتنزيل يجهز النص في الذاكرة."))


def render():
    st.set_page_config(page_title=t("المساعد البحثي · عرض الواجهة"), page_icon="◈", layout="wide", initial_sidebar_state="auto")
    st.markdown("<style>" + Path(__file__).with_name("style.css").read_text(encoding="utf-8") + "</style>", unsafe_allow_html=True)
    initialize()
    if language() == "en":
        st.markdown("""<style>
        [data-testid="stMain"], [data-testid="stSidebar"] { direction: ltr; }
        [data-testid="stMain"] [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
        [data-testid="stMain"] h1, [data-testid="stMain"] h2, [data-testid="stMain"] h3 { text-align: left; }
        .preview-note { border-right: 0; border-left: 3px solid #b3ccc7; }
        .tool-chips { justify-content: flex-start; }
        </style>""", unsafe_allow_html=True)
    st.button("English" if language() == "ar" else t("العربية"), key="ui_language_toggle",
              on_click=toggle_language, help=t("Switch interface language / تبديل لغة الواجهة"))
    sidebar()
    st.markdown(t('<div class="topline"><span>مساحة عملك البحثية / معاينة الواجهة</span><span class="demo-badge">◌ وضع تجريبي · دون بحث فعلي</span></div>'), unsafe_allow_html=True)
    if st.session_state.ui_page == PAGES[0]:
        research_page()
    elif st.session_state.ui_page == PAGES[1]:
        reports_page()
    else:
        about_page()
    st.markdown(t('<div class="footer"><span>LLM4Yemen · AI Research Assistant</span><span>معاينة محلية · بيانات توضيحية · لا اتصال بالنموذج</span></div>'), unsafe_allow_html=True)
