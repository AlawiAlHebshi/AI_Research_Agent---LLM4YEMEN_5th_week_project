# Run all seven scientific research questions sequentially, even after failures.
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
    @{ Query = 'هل توجد دراسات علمية حول تطبيق أنظمة RAG في المدارس الحكومية في عدن؟ إذا لم تتوفر أدلة كافية، وضّح ذلك.' }
    @{ Query = 'What does scientific research say about using LLMs to provide automated feedback on students'' writing?' }
    @{ Query = 'ما التحديات والحلول البحثية للتعرف الآلي على الكلام باللهجات العربية منخفضة الموارد؟' }
    @{ Query = 'قارن بين LoRA وFull Fine-Tuning من حيث الأداء واستهلاك الموارد، اعتماداً على الأبحاث المنشورة.' }
    @{ Query = 'ما أبرز نتائج الدراسات التي تناولت استخدام النماذج اللغوية الكبيرة في تقليل الهلوسة في الإجابات الطبية؟' }
    @{ Query = 'كيف يؤثر استخدام Reranking على دقة أنظمة RAG مقارنة بالاسترجاع باستخدام Embeddings فقط؟' }
    @{ Query = 'ما مدى فعالية تقنية RAG في التعليم؟ لخّص نتائج الدراسات العلمية وأبرز قيودها.' }
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
