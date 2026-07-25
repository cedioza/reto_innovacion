# plan-state.ps1 — estado compartido del flujo paralelo de planes.
#
# Unico punto de escritura de .claude/state/plans-launched.jsonl. Toda operacion
# abre el archivo con lock EXCLUSIVO (FileShare::None) y reintenta con backoff:
# 3 sesiones de /launch-plan pueden escribir a la vez sin pisarse.
#
# El JSON lo construye ESTE script desde parametros discretos (pasar JSON crudo
# por linea de comandos anidada destroza las comillas en PowerShell 5.1).
#
# Uso:
#   powershell -NoProfile -File .claude/parallel/plan-state.ps1 -Action append -Id <id> -Branch plan/<id> -PlanPath <ruta.plan.md> -Worktree <ruta-abs>
#   powershell -NoProfile -File .claude/parallel/plan-state.ps1 -Action update -Id <id> -Status pushed [-Reason "..."]
#   powershell -NoProfile -File .claude/parallel/plan-state.ps1 -Action read
#
# append fija launched_at (UTC ISO-8601) y status=running automaticamente.
# Estados validos: running | pushed | failed | merged | needs_human_review

param(
    [Parameter(Mandatory = $true)][ValidateSet('append', 'update', 'read')]
    [string]$Action,
    [string]$Id,
    [string]$Branch,
    [string]$PlanPath,
    [string]$Worktree,
    [ValidateSet('running', 'pushed', 'failed', 'merged', 'needs_human_review', '')]
    [string]$Status,
    [string]$Reason
)

$ErrorActionPreference = 'Stop'

$stateDir = Join-Path (Split-Path $PSScriptRoot -Parent) 'state'
$stateFile = Join-Path $stateDir 'plans-launched.jsonl'
if (-not (Test-Path $stateDir)) { New-Item -ItemType Directory -Force -Path $stateDir | Out-Null }

$enc = New-Object System.Text.UTF8Encoding($false)

function Open-Locked {
    param([System.IO.FileMode]$Mode, [System.IO.FileAccess]$Access)
    $attempts = 0
    while ($true) {
        try {
            return [System.IO.File]::Open($stateFile, $Mode, $Access, [System.IO.FileShare]::None)
        }
        catch [System.IO.IOException] {
            $attempts++
            if ($attempts -ge 60) { throw "No se pudo obtener el lock de $stateFile tras 60 intentos (~10s). Otro proceso lo retiene." }
            Start-Sleep -Milliseconds (100 + (Get-Random -Maximum 150))
        }
    }
}

switch ($Action) {
    'append' {
        foreach ($req in @(@('Id', $Id), @('Branch', $Branch), @('PlanPath', $PlanPath), @('Worktree', $Worktree))) {
            if (-not $req[1]) { throw "append requiere -$($req[0])." }
        }
        $entry = [ordered]@{
            id          = $Id
            branch      = $Branch
            plan_path   = $PlanPath
            worktree    = $Worktree
            launched_at = (Get-Date).ToUniversalTime().ToString('o')
            status      = 'running'
        }
        $line = ($entry | ConvertTo-Json -Compress)
        $fs = Open-Locked ([System.IO.FileMode]::Append) ([System.IO.FileAccess]::Write)
        try {
            $bytes = $enc.GetBytes($line + "`n")
            $fs.Write($bytes, 0, $bytes.Length)
        }
        finally { $fs.Close() }
        Write-Output "ok: appended $Id (launched_at=$($entry.launched_at))"
    }

    'update' {
        if (-not $Id -or -not $Status) { throw 'update requiere -Id y -Status.' }
        $fs = Open-Locked ([System.IO.FileMode]::OpenOrCreate) ([System.IO.FileAccess]::ReadWrite)
        try {
            $reader = New-Object System.IO.StreamReader($fs, $enc, $true, 4096, $true)
            $content = $reader.ReadToEnd()
            $lines = @($content -split "`n" | Where-Object { $_.Trim() })
            $found = $false
            $out = foreach ($line in $lines) {
                $obj = $line | ConvertFrom-Json
                if ($obj.id -eq $Id) {
                    $found = $true
                    $obj | Add-Member -NotePropertyName status -NotePropertyValue $Status -Force
                    $obj | Add-Member -NotePropertyName updated_at -NotePropertyValue ((Get-Date).ToUniversalTime().ToString('o')) -Force
                    if ($Reason) { $obj | Add-Member -NotePropertyName reason -NotePropertyValue $Reason -Force }
                    $obj | ConvertTo-Json -Compress -Depth 10
                }
                else { $line.Trim() }
            }
            if (-not $found) { throw "id '$Id' no existe en $stateFile" }
            $fs.SetLength(0)
            $fs.Position = 0
            $writer = New-Object System.IO.StreamWriter($fs, $enc)
            foreach ($l in $out) { $writer.WriteLine($l) }
            $writer.Flush()
        }
        finally { $fs.Close() }
        Write-Output "ok: $Id -> $Status"
    }

    'read' {
        if (Test-Path $stateFile) { Get-Content $stateFile -Encoding UTF8 } else { Write-Output '' }
    }
}
