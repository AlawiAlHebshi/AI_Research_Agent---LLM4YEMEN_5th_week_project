"""Fixed illustrative fixtures. No HTTP, environment, storage or backend imports."""

from dataclasses import replace
from typing import Callable

from frontend.contracts import Progress, ResearchRequest, ResearchResult, Scenario, Source

EXAMPLES = {
    "web": "ما هو بروتوكول MCP، وكيف يربط المساعد بالأدوات؟",
    "scientific": "ما فرص استخدام RAG في التعليم، وما حدود الأدلة المتاحة؟",
}

STEPS = (
    Progress("تجهيز السؤال التجريبي", 0.15),
    Progress("عرض مراجع توضيحية معدّة مسبقًا", 0.45),
    Progress("ترتيب العينة والاستشهادات", 0.75),
    Progress("اكتمل عرض النموذج — دون بحث فعلي", 1.0),
)


class DemoResearchError(RuntimeError):
    """An intentional UI state, never a report of an actual service failure."""


class DemoGateway:
    """The only gateway shipped with the UI: deterministic, offline demo data."""

    def research(self, request: ResearchRequest, on_progress: Callable[[Progress], None] = lambda value: None,
                 *, scenario: Scenario = "success") -> ResearchResult:
        if scenario not in {"success", "partial", "error"}:
            raise ValueError("Unknown demo scenario")
        for step in STEPS:
            on_progress(step)
            if scenario == "error" and step.fraction == 0.45:
                raise DemoResearchError("هذه محاكاة لتعذّر البحث لاختبار رسالة الخطأ؛ لم يُرسل أي طلب فعلي.")
        scientific = request.mode == "scientific"
        sources = tuple(Source(
            title=f"{'دراسة افتراضية' if scientific else 'مرجع توضيحي'} {i} — عينة واجهة",
            url=f"https://example.org/demo/{request.mode}/source-{i}",
            description=("عنوان وملخص افتراضيان، وليسا ورقة منشورة." if scientific
                         else "رابط مثال محجوز للشرح؛ لم تُفتح صفحة أو يُجرَ بحث."),
        ) for i in range(1, 4))
        if scientific:
            topic = "RAG في التعليم: عرض لشكل المقارنة البحثية"
            summary = (
                "هذه عينة مكتوبة مسبقًا لتوضيح شكل الملخص العلمي، وليست نتائج دراسات حقيقية.\n\n"
                "**الفكرة الرئيسية**\n\n"
                "ستجمع الواجهة لاحقًا ما تقوله الملخصات المتاحة، ثم تميّز نقاط الاتفاق والاختلاف "
                "وتربط كل ملاحظة بمرجعها المرقّم. يعرض هذا المثال موضع الاستشهاد الأول [1].\n\n"
                "**المقارنة بين الدراسات**\n\n"
                "يمثل المرجع الثاني مكان عرض المنهج أو سياق التجربة، مع فصل النتيجة المذكورة في الملخص "
                "عن استنتاج يحتاج إلى قراءة الورقة كاملة [2].\n\n"
                "**القيود التي يجب توضيحها**\n\n"
                "مكان مخصص لحدود البيانات وحجم العينة وقابلية تعميم النتائج. "
                "لا توجد في هذا العرض قياسات أو ادعاءات تجريبية فعلية [3]."
            )
            tools = ("search_asta", "search_openalex", "search_arxiv")
        else:
            topic = "MCP: من سؤال البحث إلى إجابة منظّمة"
            summary = (
                "هذه عينة مكتوبة مسبقًا لعرض الواجهة، وليست نتيجة بحث حي أو إجابة مولّدة عن سؤالك.\n\n"
                "**الفكرة الرئيسية**\n\n"
                "سيظهر هنا شرح موجز يجيب عن السؤال، مع إبراز المفاهيم الأساسية وربطها بالمصدر المناسب. "
                "يوضح هذا السطر موضع الاستشهاد الأول داخل الإجابة [1].\n\n"
                "**كيف تبدو التفاصيل؟**\n\n"
                "تُقسّم الإجابة إلى أفكار قصيرة يسهل قراءتها. ويمكنك فتح المرجع من رقم الاستشهاد "
                "أو الانتقال إلى تبويب المصادر لمعرفة ما يدعم كل فكرة [2].\n\n"
                "**حدود الإجابة**\n\n"
                "تظهر هنا المعلومات الناقصة أو اختلاف المصادر، بدل عرض نتيجة تبدو مكتملة بلا دليل. "
                "كل الروابط في هذه العينة توضيحية فقط [3]."
            )
            tools = ("exa_search", "wikipedia_lookup")
        if scenario == "partial":
            sources = sources[:1]
            summary = (
                "هذه محاكاة لنتيجة محدودة: مصدر توضيحي واحد فقط، ولا يوجد بحث حقيقي.\n\n"
                "يمكن عرض ملخص محدود مع استشهاد واحد [1]، مع توضيح أن المقارنة بين مصدرين غير ممكنة. "
                "لن تُضاف مراجع غير متوفرة لإكمال الشكل."
            )
        return ResearchResult(topic, summary, sources, tools, request,
                              status="partial" if scenario == "partial" else "success")


def localize_result(result: ResearchResult, language: str = "ar") -> ResearchResult:
    """Translate fixed fixtures for display, preserving IDs and the exact query."""
    if language != "en":
        return result
    scientific = result.request.mode == "scientific"
    sources = tuple(replace(source,
        title=f"{'Fictional study' if scientific else 'Illustrative reference'} {i} — UI example",
        description=("An illustrative title and abstract, not a published paper." if scientific
                     else "A reserved example link. No page was retrieved or searched."))
        for i, source in enumerate(result.sources, 1))
    if scientific:
        topic = "RAG in education: a research comparison preview"
        summary = (
            "This prepared example illustrates a scientific summary. It does not report real study findings.\n\n"
            "**Main idea**\n\n"
            "A connected interface will compare available abstracts, distinguish agreement from disagreement, "
            "and attach numbered references. This sentence illustrates the first citation [1].\n\n"
            "**Comparing studies**\n\n"
            "The second reference shows where a method or experimental setting would appear. "
            "Findings in an abstract must be distinguished from conclusions requiring a full-paper review [2].\n\n"
            "**Limitations to disclose**\n\n"
            "This section is reserved for data limitations, sample size, and generalizability. "
            "No measurements or actual experimental claims are presented in this demo [3]."
        )
    else:
        topic = "MCP: from a research question to an organized answer"
        summary = (
            "This is a prepared UI example, not live research or a generated answer to your question.\n\n"
            "**Main idea**\n\n"
            "A concise answer will explain the key concepts and connect each claim to a suitable reference. "
            "This sentence illustrates the first inline citation [1].\n\n"
            "**A readable explanation**\n\n"
            "Short sections make the answer easier to scan. Open a citation number or visit the Sources tab "
            "to review the supporting reference [2].\n\n"
            "**Limits of the answer**\n\n"
            "Missing information and differences between sources belong here, rather than a complete-looking "
            "answer without evidence. Every link in this example is illustrative only [3]."
        )
    if result.status == "partial":
        summary = (
            "This simulates a limited result: one illustrative reference and no real research.\n\n"
            "A short summary can cite the available reference [1] while explaining that a two-source comparison "
            "is unavailable. No additional references are invented to complete the layout."
        )
    return replace(result, topic=topic, summary=summary, sources=sources)
