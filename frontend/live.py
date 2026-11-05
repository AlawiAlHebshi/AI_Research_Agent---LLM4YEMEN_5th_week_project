"""Local connected UI. Research executes only inside the explicit submit branch."""

import hashlib
import html
from pathlib import Path
from uuid import uuid4

import streamlit as st

import streamlit_backend as backend
from frontend.app import linked_summary, t, toggle_language, language
from frontend.contracts import MODE_LABELS, ResearchRequest
from frontend.demo import EXAMPLES
from frontend.i18n import translate
import deployment_policy

PAGES = {"workspace": "مساحة البحث", "history": "الأبحاث السابقة", "reports": "التقارير", "about": "عن التطبيق"}


def gateway():
    if "live_gateway" not in st.session_state:
        st.session_state.live_gateway = backend.create_gateway()
    return st.session_state.live_gateway


def initialize():
    for key, value in {"ui_language": "ar", "live_page": "workspace", "live_query": "",
                       "live_mode": "web", "live_active": None, "live_error": None,
                       "live_busy": False, "live_last_signature": None}.items():
        if key not in st.session_state:
            st.session_state[key] = value


def open_history(task_id):
    try:
        st.session_state.live_active = gateway().open_history(task_id)
        st.session_state.live_error = None
        st.session_state.live_page = "workspace"
    except backend.GatewayError as error:
        st.session_state.live_error = error.message


def example(mode):
    st.session_state.live_query = t(EXAMPLES[mode])
    st.session_state.live_mode = mode
    st.session_state.live_page = "workspace"


def history_items(query="", *, prefix="recent"):
    try:
        records = gateway().history(query, limit=5)
        if not records:
            st.caption(t("لا توجد أبحاث سابقة مطابقة."))
        for record in records:
            st.button(record.topic[:70], key=f"{prefix}_{record.task_id}", width="stretch",
                      on_click=open_history, args=(record.task_id,))
            st.caption(f"{record.created_at} · {record.mode} · {record.status}")
    except backend.GatewayError as error:
        st.warning(t(error.message))


def report_controls(result):
    st.caption(t("حفظ الخادم اختياري ويتطلب موافقتك؛ تنزيل النص لا يشغّل بحثًا جديدًا."))
    confirmed = st.checkbox(t("أوافق على حفظ هذا التقرير داخل reports على هذا الجهاز"), key="live_consent_" + result.id)
    saved = gateway().saved.get(result.id)
    left, right = st.columns(2)
    with left:
        if st.button(t("حُفظ التقرير") if saved else t("حفظ التقرير"), key="live_save_" + result.id,
                     disabled=not confirmed or bool(saved), width="stretch"):
            try:
                saved = gateway().save_report(result.id, consent=confirmed)
                if saved.get("status") != "saved":
                    st.error(t("تعذّر حفظ التقرير؛ تحقق من التقارير قبل إعادة المحاولة."))
            except backend.GatewayError as error:
                st.error(t(error.message))
    with right:
        st.download_button(t("تنزيل التقرير TXT"), data=result.report.encode("utf-8"),
            file_name=f"research_{result.request.mode}_{result.id}.txt", mime="text/plain; charset=utf-8",
            key="live_download_" + result.id, width="stretch", on_click="ignore")
    if saved and saved.get("status") == "saved":
        st.success(t("حُفظ التقرير بعد موافقتك."))
        st.write(saved["filename"])


def result_view(result):
    label = t("بحث سابق — لم يُشغّل بحث جديد") if result.historical else t("نتيجة بحث متحققة")
    status = t("اكتمل مع قيود") if result.status == "degraded" else t("اكتمل البحث")
    st.markdown(f'<div class="result-top"><div><small>{html.escape(label)}</small>'
                f'<h2>{html.escape(result.topic)}</h2></div><span class="result-state">{status}</span></div>', unsafe_allow_html=True)
    st.caption(f"{result.created_at} · {result.id} · {t(MODE_LABELS[result.request.mode])}")
    st.write(result.request.query)
    if result.historical:
        st.info(t("هذه لقطة تاريخية من SQLite؛ لم تُراجع مراجعها مجددًا ولم تُرسل للنموذج."))
    if result.status == "degraded":
        st.warning(t("اكتمل البحث مع قيود: راجع نقص المصادر أو تعذّر الخدمات في الملخص."))
    if result.memory_status == "failed":
        st.warning(t("النتيجة متحققة، لكن تعذّر حفظها في ذاكرة SQLite."))
    if gateway().cloud_mode:
        st.caption(t("هذه النتيجة خاصة بالجلسة؛ نزّل التقرير للاحتفاظ به. لا تُحفظ في سجل أبحاث مشترك."))
    if not result.historical:
        metrics = st.columns(3)
        metrics[0].metric(t("المصادر"), len(result.sources))
        metrics[1].metric(t("استدعاءات النموذج"), result.model_calls)
        metrics[2].metric(t("التكلفة المحسوبة"), f"${result.cost_nanos / 1e9:.8f}")
        st.caption(f"{t('توكنات الإدخال / الإخراج')}: {result.input_tokens} / {result.output_tokens}")
    summary, sources, tools, report = st.tabs([t("الملخص"), t("المصادر"), t("الأدوات والمسار"), t("التقرير")])
    with summary:
        st.markdown(linked_summary(result))
    with sources:
        for index, source in enumerate(result.sources, 1):
            st.markdown(f'<div class="source-card"><span class="source-number">{index:02}</span><div>'
                f'<a href="{html.escape(source.url, quote=True)}" target="_blank" rel="noopener noreferrer">'
                f'{html.escape(source.title)}</a><p>{html.escape(t(source.description))}</p></div></div>', unsafe_allow_html=True)
    with tools:
        st.caption(t("أدوات البحث المسجّلة لهذه النتيجة؛ لا يعاد تشغيلها عند فتح التبويب."))
        st.markdown('<div class="tool-chips">' + "".join(f'<span class="tool-chip">{html.escape(tool)}</span>'
                    for tool in result.tools_used) + '</div>', unsafe_allow_html=True)
        if result.request.mode == "scientific":
            st.caption(t("البحث العلمي يعتمد على الملخصات والبيانات الوصفية فقط، دون قراءة الأوراق الكاملة."))
    with report:
        st.text_area(t("معاينة التقرير"), result.report, disabled=True, height=250, key="live_report_" + result.id)
        report_controls(result)


def workspace():
    st.markdown(t('<div class="hero"><div class="eyebrow">AI RESEARCH ASSISTANT</div><h1>ابدأ بسؤال.<br><span class="accent">رتّب رحلتك إلى المعرفة.</span></h1><p>مساحة واحدة لبحث الويب ومراجعة الأدبيات العلمية، مع ملخص واضح ومراجع يسهل الرجوع إليها.</p></div>'), unsafe_allow_html=True)
    with st.container(border=True, key="research_input"):
        st.radio(t("نمط البحث"), ("web", "scientific"), key="live_mode", horizontal=True,
                 format_func=lambda value, locale=language(): translate(MODE_LABELS[value], locale))
        if st.session_state.live_mode == "scientific":
            st.caption(t("البحث العلمي يعتمد على الملخصات والبيانات الوصفية فقط، دون قراءة الأوراق الكاملة."))
        st.text_area(t("ما الذي تريد استكشافه؟"), key="live_query", height=110)
        signature = hashlib.sha256((st.session_state.live_mode + "\n" + st.session_state.live_query.strip()).encode()).hexdigest()
        repeated = signature == st.session_state.live_last_signature
        repeat_key = "live_repeat_" + st.session_state.get("live_request_id", "new")
        repeat_consent = st.checkbox(t("أطلب إعادة بحث السؤال نفسه مع احتمال تكلفة جديدة"), key=repeat_key) if repeated else False
        submitted = st.button(t("ابدأ البحث"), key="start_research", type="primary", width="stretch",
                              disabled=st.session_state.live_busy or not gateway().research_enabled)
    if not gateway().configured:
        st.info(t("OPENAI_API_KEY غير مهيّأ في بيئة العملية. لم يُرسل طلب."))
    if submitted:
        if repeated and not repeat_consent:
            st.warning(t("هذه المحاولة موجودة في الجلسة؛ لإعادة البحث وافق صراحةً على التكلفة الجديدة."))
        else:
            st.session_state.live_active = None
            st.session_state.live_error = None
            try:
                request = ResearchRequest(st.session_state.live_query, st.session_state.live_mode)
                st.session_state.live_last_signature = signature
                st.session_state.live_request_id = uuid4().hex
                st.session_state.live_busy = True
                with st.status(t("جارٍ البحث والتحقق…"), expanded=True) as status:
                    progress = st.progress(0, text=t("الانتظار حتى اكتمال التحقق"))
                    try:
                        result = gateway().research(request, lambda step: progress.progress(step.fraction, text=t(step.label)),
                                                    request_id=st.session_state.live_request_id)
                    except backend.GatewayError:
                        status.update(label=t("تعذّر إكمال البحث"), state="error")
                        raise
                    status.update(label=t("اكتمل التحقق من النتيجة"), state="complete", expanded=False)
                st.session_state.live_active = result
            except (ValueError, backend.GatewayError) as error:
                st.session_state.live_error = str(error)
            finally:
                st.session_state.live_busy = False
            # Refresh history and spending after the attempt, without resubmission.
            st.rerun()
    if st.session_state.live_error:
        st.error(t(st.session_state.live_error))
        if gateway().last_usage:
            st.caption(t("قد تُحسب تكلفة للمحاولة الفاشلة؛ راجع رصيد الميزانية قبل إعادة البحث."))
    if st.session_state.live_active is not None:
        with st.container(border=True):
            result_view(st.session_state.live_active)
    elif not st.session_state.live_error:
        st.info(t("اختر النمط واكتب سؤالك. لن يبدأ بحث حتى تضغط زر البدء."))


def render():
    st.set_page_config(page_title="AI Research Assistant", page_icon="◈", layout="wide")
    initialize()
    deployment_policy.initialize_secrets(st.secrets)
    st.markdown("<style>" + Path(__file__).with_name("style.css").read_text(encoding="utf-8") + "</style>", unsafe_allow_html=True)
    if language() == "en":
        st.markdown('<style>[data-testid="stMain"],[data-testid="stSidebar"]{direction:ltr;} '
                    '[data-testid="stMarkdownContainer"],h1,h2,h3{text-align:left!important;}</style>', unsafe_allow_html=True)
    st.button("English" if language() == "ar" else "العربية", key="ui_language_toggle", on_click=toggle_language)
    try:
        gateway()
    except backend.GatewayError as error:
        st.error(t(error.message))
        return
    if gateway().cloud_mode:
        if gateway().cloud_budget_enabled:
            st.info(t("البحث السحابي متصل بسجل ميزانية دائم. لا يبدأ أي طلب دون تسجيل حجز مالي ناجح."))
            st.caption(t("التاريخ الخاص غير متاح على السحابة؛ النتائج خاصة بالجلسة وملفات التقارير على الخادم مؤقتة."))
        else:
            st.warning(t("وضع السحابة الآمن: البحث المدفوع والتاريخ الخاص مغلقان حتى تتوفر ميزانية دائمة وصلاحيات وصول مناسبة."))
            st.caption(t("SQLite وملفات runtime مؤقتة على الاستضافة؛ لا نعتمد عليها لحماية الإنفاق بعد إعادة التشغيل."))
        st.caption(t("إعداد OpenAI متاح على الخادم.") if gateway().configured else t("OPENAI_API_KEY غير مهيّأ في بيئة العملية. لم يُرسل طلب."))
        if deployment_policy.cloud_probe_enabled():
            try:
                probe = deployment_policy.free_exa_probe()
                st.caption(f"Exa MCP: {probe['status']} · {probe['result_count']} · OpenAI requests: 0")
            except Exception:
                st.caption(t("تعذّر فحص اتصال MCP المجاني؛ لم يُشغّل النموذج."))
    with st.sidebar:
        st.markdown(t('<div class="brand"><div class="brand-mark">◈</div><div><strong>المساعد البحثي</strong><small>RESEARCH STUDIO</small></div></div>'), unsafe_allow_html=True)
        st.radio(t("التنقل"), tuple(PAGES), key="live_page",
                 format_func=lambda value, locale=language(): translate(PAGES[value], locale))
        st.toggle(t("وضع العرض التجريبي"), key="ui_demo_mode")
        st.button(t("MCP وربط الأدوات"), on_click=example, args=("web",), key="live_example_web", width="stretch")
        st.button(t("RAG في التعليم"), on_click=example, args=("scientific",), key="live_example_science", width="stretch")
        st.divider()
        st.caption(t("أحدث الأبحاث المحلية"))
        history_items()
        st.caption(t("استخدام محلي لمشغّل واحد. لا يوجد تسجيل دخول أو عزل آمن متعدد المستخدمين."))
    try:
        budget = gateway().budget_status()
        st.caption(f"{t('الإنفاق المحسوب لليوم')}: \\${budget['day_nanos']/1e9:.6f} / \\$0.30 · "
                   f"{t('إجمالي المشروع')}: \\${budget['project_nanos']/1e9:.6f} / \\$5 · "
                   f"{t('حجوزات غير مسوّاة')}: \\${budget['reserved_nanos']/1e9:.6f}")
    except backend.GatewayError as error:
        st.warning(t(error.message))
    page = st.session_state.live_page
    if page == "workspace":
        workspace()
    elif page == "history":
        st.header(t("الأبحاث السابقة"))
        st.caption(t("عرض SQLite فقط؛ لا اتصال بالنموذج ولا إعادة تحقق من الروابط التاريخية."))
        query = st.text_input(t("ابحث بعنوان البحث أو السؤال"), key="live_history_search")
        history_items(query, prefix="search")
    elif page == "reports":
        st.header(t("التقارير"))
        for result_id, saved in gateway().saved.items():
            st.write(saved["filename"])
        if st.session_state.live_active is not None:
            result_view(st.session_state.live_active)
        else:
            st.info(t("افتح بحثًا سابقًا أو أكمل بحثًا جديدًا لمعاينة تقريره وتنزيله."))
    else:
        st.header(t("عن التطبيق"))
        st.write(t("هذه واجهة محلية متصلة بمحرك CLI نفسه وMCP وSQLite. البحث وحده قد يستهلك API؛ الاستعراض والحفظ والتنزيل لا يشغّلان النموذج."))
        st.write(t("حدود الإنفاق: $0.03 للمهمة، $0.30 لليوم، $5 للمشروع، و10 استدعاءات نموذج. لا تُرسل الذاكرة السابقة للنموذج."))
        st.write(t("لا تُحمّل الواجهة ملفات .env. جهّز متغيرات العملية قبل تشغيل Streamlit، ولا تدخل المفاتيح في واجهة البحث."))
