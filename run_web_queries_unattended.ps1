# Run all seven web research questions sequentially without interactive input.
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Python virtual environment not found: $python" }

$queries = @(
    @{ query = "ما أبرز المبادرات والمنظمات التي ساهمت في تطوير ريادة الأعمال التقنية في اليمن خلال السنوات الأخيرة؟" }
    @{ query = "What are the best practices for protecting API keys in publicly deployed AI applications? Cite official documentation." }
    @{ query = "كيف تعمل منصة arXiv؟ وهل جميع الأبحاث المنشورة فيها خضعت لمراجعة الأقران؟" }
    @{ query = "ما الفرق بين ترخيص MIT وترخيص Apache 2.0 من حيث حقوق الاستخدام والبراءات وإعادة التوزيع؟" }
    @{ query = "ما أحدث إصدار مستقر من Python بتاريخ 5 نوفمبر 2026؟ استند إلى الموقع الرسمي." }
    @{ query = "قارن بين Streamlit Community Cloud وRender لنشر تطبيقات Python، خصوصاً التكلفة واستمرارية تخزين SQLite." }
    @{ query = "ما هو بروتوكول MCP، ومن يطوره، وكيف يستخدم لربط وكلاء الذكاء الاصطناعي بالأدوات؟" }
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

Write-Host "`nFinished all seven queries. Succeeded: $succeeded; Failed: $failed."
