# Run all twenty scientific research questions sequentially, even after failures.
# No --save option: print results to the terminal only.
# Run from the project folder (script must be beside main.py).
$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath ".\.venv\Scripts\python.exe")) {
    Write-Host "Python environment not found: .venv\Scripts\python.exe"
    exit 1
}
if (-not (Test-Path -LiteralPath ".\main.py")) {
    Write-Host "main.py not found in the script folder."
    exit 1
}

$tasks = @(
    @{ Query = 'ما تأثير شرب القهوة على التركيز والذاكرة وفقاً للدراسات العلمية؟' }
    @{ Query = 'هل يساعد استخدام الذكاء الاصطناعي الطلاب على تحسين أدائهم الدراسي؟ ماذا تقول الأبحاث؟' }
    @{ Query = 'ما العلاقة بين قلة النوم وضعف الذاكرة والتركيز لدى طلاب الجامعات؟' }
    @{ Query = 'ما مدى فعالية استخدام روبوتات المحادثة (Chatbots) في تعليم اللغات الأجنبية؟' }
    @{ Query = 'هل تؤثر ممارسة الرياضة بانتظام على الصحة النفسية وتقليل أعراض الاكتئاب؟' }
    @{ Query = 'كيف يؤثر استخدام وسائل التواصل الاجتماعي على جودة النوم لدى المراهقين؟ لخّص أبرز نتائج الدراسات.' }
    @{ Query = 'ما تأثير التغير المناخي على إنتاج المحاصيل الزراعية، خصوصاً القمح والأرز؟' }
    @{ Query = 'ما الفرق بين التعلم باستخدام الفيديوهات التعليمية والتعلم من الكتب من حيث فهم المعلومات والاحتفاظ بها؟' }
    @{ Query = 'هل توجد أدلة علمية على أن الاستماع إلى الموسيقى أثناء الدراسة يحسن التركيز أو يضعفه؟' }
    @{ Query = 'ما أبرز نتائج الدراسات التي تقارن بين السيارات الكهربائية والسيارات التقليدية من حيث تأثيرها البيئي؟' }
    @{ Query = 'كيف يمكن استخدام التعلم الآلي (Machine Learning) للكشف المبكر عن الأمراض؟ وما أبرز التحديات المتعلقة بدقة التشخيص؟' }
    @{ Query = 'ما تأثير استخدام الهواتف الذكية قبل النوم على جودة النوم ومدته؟' }
    @{ Query = 'هل أظهرت الدراسات أن التعليم عن بُعد يحقق نتائج مشابهة للتعليم الحضوري لدى طلاب الجامعات؟' }
    @{ Query = 'ما مدى فعالية تقنيات معالجة اللغة الطبيعية (NLP) في تحليل المشاعر في النصوص العربية؟' }
    @{ Query = 'ما العلاقة بين النشاط البدني المنتظم وتحسين وظائف الذاكرة لدى كبار السن؟' }
    @{ Query = 'هل تستطيع النماذج اللغوية الكبيرة (LLMs) تقديم إجابات طبية دقيقة مقارنة بالمختصين؟ وما أهم القيود التي كشفتها الدراسات؟' }
    @{ Query = 'ما تأثير التلوث البلاستيكي الدقيق (Microplastics) على الكائنات البحرية وفقاً للأبحاث المنشورة؟' }
    @{ Query = 'ما مدى فعالية استخدام الواقع الافتراضي (VR) في التعليم مقارنة بالطرق التقليدية؟' }
    @{ Query = 'هل أظهرت الأبحاث أن استخدام تقنيات RAG يقلل من الهلوسة في إجابات النماذج اللغوية الكبيرة؟ وما حدود هذا التحسن؟' }
    @{ Query = 'هل توجد دراسات علمية تقيس تأثير استخدام أدوات الذكاء الاصطناعي على مستوى التفكير النقدي لدى طلاب الجامعات؟ وما النتائج التي توصلت إليها؟' }
)

$failedQueries = @()
for ($i = 0; $i -lt $tasks.Count; $i++) {
    Write-Host "`n=== Starting scientific query $($i + 1) / $($tasks.Count) ===" -ForegroundColor Cyan
    $commandArgs = @("-B", "main.py", "--mode", "scientific", "--query", $tasks[$i].Query, "--verbose")
    $exitCode = 1

    try {
        # Send an empty input stream so any unexpected input prompt cannot wait for a person.
        @() | & ".\.venv\Scripts\python.exe" @commandArgs
        $exitCode = $LASTEXITCODE
    }
    catch {
        Write-Warning "Query $($i + 1) raised an error: $($_.Exception.Message)"
    }

    if ($exitCode -ne 0) {
        $failedQueries += ($i + 1)
        Write-Warning "Query $($i + 1) failed (exit code $exitCode). Moving on to the next query."
    }
    else {
        Write-Host "=== Query $($i + 1) completed ===" -ForegroundColor Green
    }
}

Write-Host "`n=== All $($tasks.Count) queries attempted ===" -ForegroundColor Cyan
Write-Host "Succeeded: $($tasks.Count - $failedQueries.Count) | Failed: $($failedQueries.Count)"
if ($failedQueries.Count -gt 0) {
    Write-Warning "Failed query numbers: $($failedQueries -join ', ')"
}
