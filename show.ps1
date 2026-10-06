# Repelnt backend trace, menu driven. Handles the folder and the virtualenv, so
# a live demo does not turn into a path-debugging session.
#
#   .\show.ps1              pick traces from a menu, as many times as you like
#   .\show.ps1 gptbot       run one and exit
#   .\show.ps1 gptbot survey   run one against another page, and exit
param(
    [string]$Profile = "",
    [string]$Page = "research"
)

$ErrorActionPreference = "Stop"
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

$CHOICES = [ordered]@{
    "1" = @("human",    "a person in Chrome, gets the real page")
    "2" = @("gptbot",   "a declared AI crawler, caught on its headers")
    "3" = @("trapped",  "flawless headers, caught by its behaviour")
    "4" = @("pricebot", "a script using library defaults")
    "5" = @("mimic",    "flawless headers, not yet trapped")
    "6" = @("empty",    "no user-agent at all")
}

if (-not (Test-Path $py)) {
    Write-Host "No interpreter at $py" -ForegroundColor Red
    Write-Host "Create it with:  python -m venv .venv"
    Write-Host "Then:            .\.venv\Scripts\pip.exe install -r requirements.txt"
    exit 1
}

function Invoke-Trace([string]$name, [string]$page) {
    Write-Host ""
    & $py "demo\trace.py" $name $page
    Write-Host ""
}

function Show-Menu {
    Write-Host ""
    Write-Host "  REPELNT BACKEND TRACE" -ForegroundColor Cyan
    Write-Host "  page: $Page" -ForegroundColor DarkGray
    Write-Host ""
    foreach ($k in $CHOICES.Keys) {
        $name, $blurb = $CHOICES[$k]
        Write-Host ("   {0}   {1,-10} {2}" -f $k, $name, $blurb)
    }
    Write-Host ""
    Write-Host "   a   all three presentation traces, in order"
    Write-Host "   q   quit"
    Write-Host ""
}

Push-Location $PSScriptRoot
try {
    # A profile on the command line means one run, no menu.
    if ($Profile -ne "") {
        Invoke-Trace $Profile $Page
        return
    }

    # Nothing to read from (piped, redirected, CI): just run the three.
    if (-not [Environment]::UserInteractive -or [Console]::IsInputRedirected) {
        foreach ($p in @("human", "gptbot", "trapped")) { Invoke-Trace $p $Page }
        return
    }

    while ($true) {
        Show-Menu
        $pick = (Read-Host "  choose").Trim().ToLower()

        if ($pick -eq "" -or $pick -eq "q" -or $pick -eq "quit") { break }

        if ($pick -eq "a" -or $pick -eq "all") {
            foreach ($p in @("human", "gptbot", "trapped")) { Invoke-Trace $p $Page }
            continue
        }

        if ($CHOICES.Contains($pick)) {
            Invoke-Trace $CHOICES[$pick][0] $Page
            continue
        }

        # Typing the profile name works too, since that is the natural reflex.
        $names = @(); foreach ($k in $CHOICES.Keys) { $names += $CHOICES[$k][0] }
        if ($names -contains $pick) {
            Invoke-Trace $pick $Page
            continue
        }

        Write-Host "  not a choice: '$pick'" -ForegroundColor Yellow
    }
}
finally {
    Pop-Location
}
