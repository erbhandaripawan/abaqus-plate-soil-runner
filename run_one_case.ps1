param(
    [Parameter(Mandatory = $true)]
    [string]$CaseConfig,

    [string]$AbaqusCommand = "abaqus",

    [switch]$SkipSubmit,
    [switch]$SkipExcel
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$casePath = Resolve-Path -LiteralPath $CaseConfig
$skipSubmitArg = ""
if ($SkipSubmit) {
    $skipSubmitArg = "--skip-submit"
}

Write-Host "Running Abaqus build/extract for $casePath"
& $AbaqusCommand cae noGUI=src\abaqus_build_run.py -- --config "$casePath" $skipSubmitArg

if (-not $SkipSubmit) {
    & $AbaqusCommand python src\abaqus_extract_odb.py -- --config "$casePath"
}

if (-not $SkipExcel) {
    if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
        throw "Missing .venv. Run .\setup_venv.ps1 first."
    }
    & ".\.venv\Scripts\python.exe" src\make_workbook.py --case "$casePath"
}

Write-Host "Done."

