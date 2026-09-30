# <REPO> = this repo root. <DRIVE> = the user-profile root that holds .claude\skills.
$R = "<REPO>"
$B = "$R\method\agent-briefs"
function Base($t) { if ($t -eq "ibn_kathir") { "$R\data\v2" } else { "$R\data\multi\$t" } }
function Test-Moves($t, $w, $ann) {
  $base = Base $t
  $f = "$base\moves\$ann\$w.json"
  if (-not (Test-Path $f)) { return $false }
  python -c "import json,sys; m=json.load(open(r'$f',encoding='utf-8')); p=json.load(open(r'$base\packets\$w.json',encoding='utf-8')); ids={s['id'] for s in p.get('spans',[])}; mv=m['moves'] if isinstance(m,dict) else m; bad=[i for x in mv for i in x.get('span_ids',[])+x.get('evidence_span_ids',[]) if i not in ids]; sys.exit(1 if (bad or not mv) else 0)" 2>$null
  return ($LASTEXITCODE -eq 0)
}
# model chain: annotator folder, relay, model
$chain = @(
  @("deepseek","cline","cline-free/deepseek-v4.1-flash"),
  @("mimo","cline","cline-free/mimo-v2.6-flash"),
  @("muse","cline","cline-free/muse-spark-1.3"),
  @("grok45","cursor","cursor-grok-4.5-high")
)
$jobs = @(
  @("ibn_kathir","2_102"), @("ibn_kathir","2_255_tafsir"),
  @("al_baghawi","17_105"), @("al_baghawi","2_102"), @("al_baghawi","2_255"),
  @("al_tabari","17_105"), @("al_tabari","2_102"), @("al_tabari","2_255")
)
foreach ($j in $jobs) {
  $t = $j[0]; $w = $j[1]
  Write-Output "=== $t $w ==="
  $done = $false
  foreach ($c in $chain) { if (Test-Moves $t $w $c[0]) { Write-Output "$($c[0]) : already done"; $done = $true; break } }
  if ($done) { continue }
  foreach ($c in $chain) {
    $ann = $c[0]
    $bf = "$B\brief_multi_B2_${t}_$w.txt"
    if ($ann -ne "deepseek") {
      $bf2 = "$B\brief_multi_B2_${t}_${w}_$ann.txt"
      (Get-Content $bf -Raw).Replace("moves/deepseek", "moves/$ann") | Set-Content -Encoding utf8 $bf2
      $bf = $bf2
    }
    $relay = if ($c[1] -eq "cline") { "<DRIVE>\.claude\skills\cline-delegate\scripts\relay.mjs" } else { "<DRIVE>\.claude\skills\cursor-delegate\scripts\relay.mjs" }
    $p = Start-Process -FilePath node -ArgumentList @("`"$relay`"","--brief","`"$bf`"","--cd","`"$R`"","--model",$c[2],"--timeout","30m") -NoNewWindow -PassThru
    if (-not $p.WaitForExit(35 * 60 * 1000)) { Write-Output "${ann}: hard timeout, killing"; Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    if (Test-Moves $t $w $ann) { Write-Output "${ann}: OK"; $done = $true; break } else { Write-Output "${ann}: FAILED" }
  }
  if (-not $done) { Write-Output "ALL MODELS FAILED for $t $w" }
}
Write-Output "=== CHAIN FINISHED ==="
