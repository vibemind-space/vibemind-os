# n8n workflow + credential setup
#
# Voraussetzungen:
#   - n8n läuft auf http://127.0.0.1:15678 (vibemind-n8n container)
#   - Du hast einen n8n-account (UI bei :15678) + API-Key
#
# Vorgehen:
#   1. n8n-UI öffnen: http://127.0.0.1:15678
#   2. Settings → n8n API → API-Keys → Create new
#   3. Diesen Key in env-var setzen: $env:N8N_API_KEY = "..."
#   4. Dann dieses Script ausführen: .\import.ps1
#
# Was passiert:
#   - Lädt 3 workflow-JSONs (01_inbound_classifier, 02_reply_enrichment, 03_approval_orchestrator)
#   - Liest MARKETING_N8N_API_KEY aus repo-root .env
#   - Erstellt n8n "Header Auth" credential namens "Marketing n8n API key"
#   - Importiert die 3 workflows und assigniert ihnen die credential
#   - Aktiviert sie alle

param(
    [string]$N8nBase = "http://127.0.0.1:15678",
    [string]$EnvFile = "c:\Users\User\Desktop\Vibemind_V1\.env"
)

if (-not $env:N8N_API_KEY) {
    Write-Host "ERROR: \$env:N8N_API_KEY ist nicht gesetzt." -ForegroundColor Red
    Write-Host ""
    Write-Host "So bekommst du den n8n API-Key:" -ForegroundColor Yellow
    Write-Host "  1. http://127.0.0.1:15678 im Browser oeffnen"
    Write-Host "  2. Settings -> n8n API -> Create an API key"
    Write-Host "  3. Den Key kopieren"
    Write-Host "  4. \$env:N8N_API_KEY = '<key>'"
    Write-Host "  5. .\import.ps1 erneut ausfuehren"
    exit 1
}

# Marketing key aus .env lesen
$marketingKey = ""
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^MARKETING_N8N_API_KEY\s*=\s*(.+)$') {
        $marketingKey = $Matches[1].Trim('"').Trim("'")
    }
}
if (-not $marketingKey) {
    Write-Host "ERROR: MARKETING_N8N_API_KEY in $EnvFile nicht gefunden." -ForegroundColor Red
    exit 1
}
Write-Host "Marketing API-Key gefunden (len: $($marketingKey.Length))" -ForegroundColor Green

$hdr = @{
    "X-N8N-API-KEY" = $env:N8N_API_KEY
    "Content-Type" = "application/json"
}

# Schritt 1: Credential anlegen
Write-Host "`n=== Schritt 1: Credential 'Marketing n8n API key' ==="
$credBody = @{
    name = "Marketing n8n API key"
    type = "httpHeaderAuth"
    data = @{
        name = "Authorization"
        value = "Bearer $marketingKey"
    }
} | ConvertTo-Json

try {
    $cred = Invoke-RestMethod -Uri "$N8nBase/api/v1/credentials" -Method POST -Headers $hdr -Body $credBody
    $credId = $cred.id
    Write-Host "  Credential erstellt: id=$credId" -ForegroundColor Green
} catch {
    if ($_.ErrorDetails.Message -like "*already exists*") {
        Write-Host "  Credential existiert bereits — suche id..."
        $creds = Invoke-RestMethod -Uri "$N8nBase/api/v1/credentials" -Headers $hdr
        $cred = $creds.data | Where-Object { $_.name -eq "Marketing n8n API key" } | Select-Object -First 1
        $credId = $cred.id
        Write-Host "  Existierende Credential gefunden: id=$credId"
    } else {
        Write-Host "  FEHLER: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "  Body: $($_.ErrorDetails.Message)" -ForegroundColor Red
        exit 1
    }
}

# Schritt 2: Workflows importieren
Write-Host "`n=== Schritt 2: Workflows importieren ==="

# Idempotenz: existierende Workflows (per Name) nicht doppelt importieren.
# (2026-07-09: 01-03 waren bereits importiert — Blind-Import = Duplikate.)
$existingNames = @{}
try {
    $existing = Invoke-RestMethod -Uri "$N8nBase/api/v1/workflows" -Headers $hdr
    foreach ($w in $existing.data) { $existingNames[$w.name] = $w.id }
    Write-Host "  $($existingNames.Count) Workflow(s) bereits in n8n" -ForegroundColor Gray
} catch {
    Write-Host "  WARN: Workflow-Liste nicht abrufbar - fahre ohne Duplikat-Check fort" -ForegroundColor Yellow
}
$workflowDir = "c:\Users\User\Desktop\Vibemind_V1\spaces\marketing\n8n_workflows"
$workflowFiles = @(
    "01_inbound_classifier.json",
    "02_reply_enrichment.json",
    "03_approval_orchestrator.json",
    # Schicht 8.0 Phase 4 — one isolated broadcast workflow per channel
    # (routing is channel-aware in the webhook bus, migration 038).
    # 06_email fehlt bewusst: send_worker ist CLI ohne HTTP-Surface,
    # broadcasts != campaigns — braucht erst eine Bridge (Phase 6b).
    "04_linkedin_broadcast.json",
    "05_x_broadcast.json",
    "07_discord_broadcast.json",
    "08_telegram_broadcast.json"
)

# Broadcast-Workflows: nach erfolgreichem Import + Aktivierung wird die
# zugehoerige (in Migration 038 mit active=false geseedete) Bus-Subscription
# scharfgeschaltet — sonst liefen Approvals gegen einen fehlenden Webhook
# in 404-Retries.
$broadcastChannelByFile = @{
    "04_linkedin_broadcast.json" = "linkedin"
    "05_x_broadcast.json"        = "x"
    "07_discord_broadcast.json"  = "discord"
    "08_telegram_broadcast.json" = "telegram"
}

function Enable-BusSubscription([string]$channel) {
    $db = docker ps --format "{{.Names}}" 2>$null | Select-String "supabase-db" | Select-Object -First 1
    if (-not $db) {
        Write-Host "    -> Bus-Subscription NICHT aktiviert (supabase-db nicht gefunden)" -ForegroundColor Yellow
        return
    }
    $sql = "UPDATE marketing.webhook_subscriptions SET active = true, disabled_at = NULL " +
           "WHERE name = 'n8n-$channel-broadcast' RETURNING name"
    $out = docker exec $db.ToString().Trim() psql -U supabase_admin -d postgres -tAc $sql 2>&1
    if ($out -match "n8n-$channel-broadcast") {
        Write-Host "    -> Bus-Subscription 'n8n-$channel-broadcast' aktiviert" -ForegroundColor Green
    } else {
        Write-Host "    -> Bus-Subscription-Aktivierung unklar: $out" -ForegroundColor Yellow
    }
}

foreach ($wfFile in $workflowFiles) {
    $path = Join-Path $workflowDir $wfFile
    if (-not (Test-Path $path)) {
        Write-Host "  $wfFile FEHLT: $path" -ForegroundColor Red
        continue
    }
    $wfJson = Get-Content $path -Raw | ConvertFrom-Json
    if ($existingNames.ContainsKey($wfJson.name)) {
        Write-Host "  $wfFile -> '$($wfJson.name)' existiert bereits (id=$($existingNames[$wfJson.name])) - SKIP" -ForegroundColor Gray
        continue
    }
    # Marketing-API-Credential nur an die Nodes haengen, die WIRKLICH gegen
    # die Marketing-API sprechen. Discord nutzt ebenfalls httpHeaderAuth
    # (Authorization: Bot <token>) - ein blindes Ueberschreiben aller
    # httpHeaderAuth-Nodes wuerde dem Discord-Node den Marketing-Key
    # unterschieben (Bug 2026-07-13, hier gefixt). Erkennungsmerkmal:
    # Platzhalter-IDs (REPLACE_ME_*) bleiben unangetastet und muessen einmalig
    # in der n8n-UI bzw. per Script mit der echten Credential verbunden werden.
    foreach ($node in $wfJson.nodes) {
        if ($node.credentials -and $node.credentials.httpHeaderAuth) {
            $curId = [string]$node.credentials.httpHeaderAuth.id
            if ($curId -like "REPLACE_ME*") {
                Write-Host "    [!] $($node.name): Platzhalter-Credential ($curId) - bleibt offen" -ForegroundColor Yellow
                continue
            }
            $node.credentials.httpHeaderAuth.id = $credId
            $node.credentials.httpHeaderAuth.name = "Marketing n8n API key"
        }
    }
    # n8n API will nur die workflow-schema-felder
    $importPayload = @{
        name = $wfJson.name
        nodes = $wfJson.nodes
        connections = $wfJson.connections
        settings = $wfJson.settings
    } | ConvertTo-Json -Depth 20

    try {
        $r = Invoke-RestMethod -Uri "$N8nBase/api/v1/workflows" -Method POST -Headers $hdr -Body $importPayload
        $wfId = $r.id
        Write-Host "  $wfFile -> workflow_id=$wfId" -ForegroundColor Green
        # Aktivieren
        try {
            Invoke-RestMethod -Uri "$N8nBase/api/v1/workflows/$wfId/activate" -Method POST -Headers $hdr | Out-Null
            Write-Host "    -> aktiviert" -ForegroundColor Green
            # Broadcast-Workflow? Dann die Bus-Subscription scharfschalten.
            if ($broadcastChannelByFile.ContainsKey($wfFile)) {
                Enable-BusSubscription -channel $broadcastChannelByFile[$wfFile]
            }
        } catch {
            Write-Host "    -> aktivierung fehlgeschlagen: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  $wfFile FEHLER: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "  Body: $($_.ErrorDetails.Message)" -ForegroundColor Red
    }
}

Write-Host "`n=== Fertig ===" -ForegroundColor Green
Write-Host "Naechster Schritt: webhook-subscriptions anlegen (siehe register_webhooks.ps1)" -ForegroundColor Cyan
