[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Output,
    [ValidateRange(1, 5)][int]$Repeat = 2,
    [ValidateRange(1, 60)][int]$WaitSeconds = 3,
    [string]$OpenCli = "opencli"
)

$ErrorActionPreference = "Stop"
# OpenCLI emits UTF-8 JSON; prevent Windows PowerShell 5.1 from decoding
# Unicode titles as an ANSI code page before ConvertFrom-Json.
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
& "$env:SystemRoot\System32\chcp.com" 65001 | Out-Null
$rankSpecs = @(
    [pscustomobject]@{ Id = "monthly_ticket"; Label = "monthly-ticket"; Url = "https://www.qidian.com/rank/yuepiao/" },
    [pscustomobject]@{ Id = "hot_sales"; Label = "hot-sales"; Url = "https://www.qidian.com/rank/hotsales/" },
    [pscustomobject]@{ Id = "read_index"; Label = "read-index"; Url = "https://www.qidian.com/rank/readindex/" },
    [pscustomobject]@{ Id = "recommendation"; Label = "recommendation"; Url = "https://www.qidian.com/rank/recom/" },
    [pscustomobject]@{ Id = "new_book"; Label = "new-book"; Url = "https://www.qidian.com/rank/signNewBkAll/" }
)
$session = "novel-analyzer-qidian-$PID"
$outputPath = [System.IO.Path]::GetFullPath($Output)
[System.IO.Directory]::CreateDirectory($outputPath) | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Write-Utf8Json([string]$Path, $Value) {
    $json = $Value | ConvertTo-Json -Depth 30
    [System.IO.File]::WriteAllText($Path, $json + "`n", $utf8)
}

$extractJs = @"
JSON.stringify({
  url: location.href,
  title: document.title,
  captured_at: new Date().toISOString(),
  items: [...document.querySelectorAll('.book-img-text li')].map((li, i) => {
    const clone = li.cloneNode(true);
    clone.querySelectorAll('style').forEach(s => s.remove());
    return {
      position: i + 1,
      title: clone.querySelector('h2 a')?.textContent.trim() || null,
      url: clone.querySelector('h2 a')?.href || null,
      author: clone.querySelector('.author .name')?.textContent.trim() || clone.querySelector('.author a')?.textContent.trim() || null,
      categories: [...clone.querySelectorAll('.author a')].slice(1).map(x => x.textContent.trim()),
      intro: clone.querySelector('.intro')?.textContent.trim() || null,
      latest_update: clone.querySelector('.update')?.textContent.trim() || null,
      metric_text: clone.querySelector('.total')?.textContent.trim() || clone.querySelector('.rank-tag')?.textContent.trim() || null
    };
  })
})
"@
$extractJs = ($extractJs -replace "\r?\n", " ").Trim()

$captures = @()
$orderedRuns = @()
try {
    for ($run = 1; $run -le $Repeat; $run++) {
        $runLists = @()
        $runIds = @()
        foreach ($spec in $rankSpecs) {
            # Retry a transiently unloaded page once, but NEVER accept a redirect
            # or a list with fewer than 20 verified book rows.
            $raw = $null
            $lastError = ""
            for ($attempt = 1; $attempt -le 2; $attempt++) {
                & $OpenCli browser $session open $spec.Url --window background | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    $lastError = "opencli open failed"
                    continue
                }
                & $OpenCli browser $session wait time $WaitSeconds | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    $lastError = "opencli wait failed"
                    continue
                }
                $rawText = (& $OpenCli browser $session eval $extractJs | Out-String).Trim()
                if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($rawText)) {
                    $lastError = "opencli eval returned no JSON"
                    continue
                }
                try {
                    $raw = $rawText | ConvertFrom-Json -ErrorAction Stop
                } catch {
                    $raw = $null
                    $lastError = "opencli eval returned invalid JSON"
                    continue
                }
                if ($raw.url.StartsWith($spec.Url) -and $raw.items.Count -ge 20) {
                    break
                }
                $lastError = "unexpected page URL or fewer than 20 books"
            }
            if ($null -eq $raw -or -not $raw.url.StartsWith($spec.Url) -or $raw.items.Count -lt 20) {
                $actualUrl = if ($null -eq $raw) { "none" } else { $raw.url }
                $actualCount = if ($null -eq $raw) { 0 } else { $raw.items.Count }
                throw "Qidian page contract failed for $($spec.Id): url=$actualUrl, items=$actualCount; $lastError"
            }
            $bad = @($raw.items | Where-Object { [string]::IsNullOrWhiteSpace($_.title) -or [string]::IsNullOrWhiteSpace($_.url) })
            if ($bad.Count -gt 0) { throw "Qidian $($spec.Id) contains $($bad.Count) empty title/url entries" }
            $rawFile = "raw_$($spec.Id)_$($run.ToString('00')).json"
            Write-Utf8Json (Join-Path $outputPath $rawFile) $raw
            $items = @($raw.items | ForEach-Object {
                [pscustomobject]@{
                    platform = "qidian"
                    source_id = "qidian_paid_trend_target"
                    list_id = $spec.Id
                    list_label = $spec.Label
                    position = [int]$_.position
                    title = $_.title
                    url = $_.url
                    author = $_.author
                    categories = @($_.categories)
                    intro = $_.intro
                    latest_update = $_.latest_update
                    metric_text = $_.metric_text
                    metric_encoding = "qidian_dynamic_font_may_be_obfuscated"
                    captured_at = $raw.captured_at
                }
            })
            $runIds += @($items | ForEach-Object { "$($spec.Id):$($_.url)" })
            $runLists += [pscustomobject]@{ list_id = $spec.Id; list_label = $spec.Label; items = $items }
            $captures += [pscustomobject]@{
                run = $run
                list_id = $spec.Id
                captured_at = $raw.captured_at
                final_url = $raw.url
                item_count = $items.Count
                raw_file = $rawFile
                raw_sha256 = (Get-FileHash (Join-Path $outputPath $rawFile) -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
        $allUrls = @($runLists | ForEach-Object { $_.items } | ForEach-Object { $_.url } | Sort-Object -Unique)
        $normalized = [pscustomobject]@{
            source = "qidian_paid_trend_target"
            captured_at = [DateTime]::UtcNow.ToString("o")
            required_list_ids = @($rankSpecs | ForEach-Object { $_.Id })
            lists = $runLists
            stats = [pscustomobject]@{ list_count = $runLists.Count; rank_slots = $runIds.Count; unique_book_count = $allUrls.Count }
        }
        Write-Utf8Json (Join-Path $outputPath "normalized_$($run.ToString('00')).json") $normalized
        $orderedRuns += ,$runIds
    }
} finally {
    & $OpenCli browser $session close 2>$null | Out-Null
}

$pairs = @()
for ($index = 1; $index -lt $orderedRuns.Count; $index++) {
    $left = @($orderedRuns[$index - 1])
    $right = @($orderedRuns[$index])
    $overlap = @($left | Where-Object { $right -contains $_ } | Sort-Object -Unique).Count
    $pairs += [pscustomobject]@{
        pair = $index
        left_count = $left.Count
        right_count = $right.Count
        overlap_count = $overlap
        exact_ordered_ids = (($left -join "`n") -ceq ($right -join "`n"))
    }
}
Write-Utf8Json (Join-Path $outputPath "reproducibility.json") ([pscustomobject]@{ repeat_count = $Repeat; pairs = $pairs })
$manifest = [pscustomobject]@{
    source = "qidian_paid_trend_target"
    acquisition = "opencli_chrome_bridge_fixed_urls_and_dom_contract"
    captured_at = [DateTime]::UtcNow.ToString("o")
    repeat_count = $Repeat
    required_list_ids = @($rankSpecs | ForEach-Object { $_.Id })
    captures = $captures
    reproducibility_file = "reproducibility.json"
    evidence_class = "verified_current_public_rank_via_browser"
    limitation = "Qidian numeric metrics may use a dynamic font; titles, authors, categories, introductions, updates and ordered URLs remain directly auditable."
}
Write-Utf8Json (Join-Path $outputPath "manifest.json") $manifest
$manifest | ConvertTo-Json -Depth 20
