# Run all 20 web research questions sequentially without interactive input.
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Python virtual environment not found: $python" }

$queries = @(
    @{ query = "ما هي أكبر خمس دول في العالم من حيث المساحة، وكم تبلغ مساحة كل منها؟" }
    @{ query = "كيف تعمل الألواح الشمسية على توليد الكهرباء، وما أبرز مميزاتها وعيوبها؟" }
    @{ query = "ما أسباب أزمة المياه في اليمن، وما أبرز الحلول المقترحة لمعالجتها؟" }
    @{ query = "من اخترع الإنترنت، وكيف تطور منذ بداياته حتى اليوم؟" }
    @{ query = "ما الفرق بين الطاقة الشمسية وطاقة الرياح من حيث التكلفة والكفاءة والأثر البيئي؟" }
    @{ query = "ما هي منظمة الأمم المتحدة، ومتى تأسست، وما أبرز إنجازاتها؟" }
    @{ query = "ما أبرز المواقع الأثرية في اليمن، وما أهميتها التاريخية؟" }
    @{ query = "كيف يؤثر استخدام وسائل التواصل الاجتماعي على الصحة النفسية للمراهقين؟" }
    @{ query = "ما الفرق بين الفيروسات والبكتيريا، وكيف تختلف طرق علاج الأمراض التي تسببها؟" }
    @{ query = "ما أسباب ارتفاع أسعار الذهب وانخفاضها، وما العوامل التي تؤثر على قيمته عالمياً؟" }
    @{ query = "ما أهم الاكتشافات التي حققها تلسكوب جيمس ويب الفضائي منذ إطلاقه؟" }
    @{ query = "ما الفرق بين التعليم الحضوري والتعليم عن بُعد، وما أبرز مميزات وتحديات كل منهما؟" }
    @{ query = "كيف تعمل العملات الرقمية مثل البيتكوين، وما أبرز المخاطر المرتبطة باستخدامها؟" }
    @{ query = "ما أكبر خمس شركات تقنية في العالم من حيث القيمة السوقية في نوفمبر 2026، وما أبرز منتجاتها؟" }
    @{ query = "كيف يؤثر التغير المناخي على الزراعة والأمن الغذائي في الدول النامية؟" }
    @{ query = "ما الفرق بين النظام الرئاسي والنظام البرلماني، وما أمثلة الدول التي تستخدم كلاً منهما؟" }
    @{ query = "ما أبرز التطورات التي شهدتها السيارات الكهربائية خلال السنوات الأخيرة، وما التحديات التي تواجه انتشارها؟" }
    @{ query = "ما هي منظمة الصحة العالمية، وما دورها في مكافحة الأمراض والأوبئة؟" }
    @{ query = "كيف يؤثر العمل عن بُعد على إنتاجية الموظفين، وما أبرز إيجابياته وسلبياته؟" }
    @{ query = "ما أبرز المبادرات التي تدعم الشباب ورواد الأعمال في اليمن، وما الخدمات التي تقدمها؟" }
)

$succeeded = 0
$failed = 0

for ($i = 0; $i -lt $queries.Count; $i++) {
    Write-Host "`nRunning web query $($i + 1) of $($queries.Count)..."
    $arguments = @("-B", "main.py", "--mode", "web", "--query", $queries[$i].query, "--verbose")
    # Pipe an empty line and then EOF to avoid waiting indefinitely for input().
    try {
        "" | & $python @arguments
        $exitCode = $LASTEXITCODE
    }
    catch {
        $exitCode = 1
        Write-Warning "Query $($i + 1) raised an error: $_"
    }

    if ($exitCode -ne 0) {
        $failed++
        Write-Warning "Query $($i + 1) failed (exit code $exitCode). Continuing to the next query."
        continue
    }
    $succeeded++
}

Write-Host "`nFinished all 20 queries. Succeeded: $succeeded; Failed: $failed."
