# Webhook-subscriptions registration
#
# Registriert 3 webhook_subscriptions in marketing-API die die n8n workflows
# triggern. Eines pro workflow.
#
# Idempotent — duplicates werden uebersprungen (409 conflict-unique).

param(
    [string]$MarketingBase = "http://127.0.0.1:5510",
    [string]$EnvFile = "c:\Users\User\Desktop\Vibemind_V1\.env",
    [string]$N8nBaseInternal = "http://host.docker.internal:5678"  # how marketing-API reaches n8n
)

# Marketing PROPOSAL key aus .env
$proposalKey = ""
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^MARKETING_PROPOSAL_API_KEY\s*=\s*(.+)$') {
        $proposalKey = $Matches[1].Trim('"').Trim("'")
    }
}
if (-not $proposalKey) {
    Write-Host "ERROR: MARKETING_PROPOSAL_API_KEY in $EnvFile nicht gefunden." -ForegroundColor Red
    exit 1
}

# 3 subscriptions
$subs = @(
    @{
        name = "n8n-inbound-classifier"
        events = @("inbound_received")
        n8n_path = "marketing-inbound-classifier"
    },
    @{
        name = "n8n-reply-enrichment"
        events = @("inbound_classified")
        n8n_path = "marketing-reply-enrichment"
    },
    @{
        name = "n8n-approval-orchestrator"
        events = @("reply_proposal_status_changed")
        n8n_path = "marketing-approval-orchestrator"
    }
)

# Existing subs holen
$hdr = @{ "X-API-Key" = $proposalKey }
try {
    $existing = Invoke-RestMethod -Uri "$MarketingBase/api/webhook_subscriptions" -Headers $hdr -Method Get
} catch {
    Write-Host "FEHLER beim Subscription-List: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host "=== Webhook-subscriptions ==="
foreach ($sub in $subs) {
    $existingMatch = $existing.data | Where-Object { $_.name -eq $sub.name }
    if ($existingMatch) {
        Write-Host "  $($sub.name) -> existiert (id=$($existingMatch.id), active=$($existingMatch.active))" -ForegroundColor Yellow
        continue
    }

    # Generate signing secret per subscription
    $secret = (& "c:\Users\User\Desktop\Vibemind_V1\.venv\Scripts\python.exe" -c "import secrets; print(secrets.token_urlsafe(48))").Trim()

    $url = "$N8nBaseInternal/webhook/$($sub.n8n_path)"
    $body = @{
        api_key = $proposalKey
        name = $sub.name
        url = $url
        events = $sub.events
        secret = $secret
    } | ConvertTo-Json -Compress

    try {
        $r = Invoke-RestMethod -Uri "$MarketingBase/api/webhook_subscriptions" -Method POST -Body $body -ContentType "application/json"
        Write-Host "  $($sub.name) -> ANGELEGT (id=$($r.data.id))" -ForegroundColor Green
        Write-Host "    url: $url"
        Write-Host "    events: $($sub.events -join ', ')"
        Write-Host "    secret-prefix: $($secret.Substring(0,8))..."
    } catch {
        Write-Host "  $($sub.name) -> FEHLER: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "    Body: $($_.ErrorDetails.Message)" -ForegroundColor Red
    }
}

Write-Host "`n=== Verify ==="
$final = Invoke-RestMethod -Uri "$MarketingBase/api/webhook_subscriptions" -Headers $hdr
$marketing = $final.data | Where-Object { $_.name -like "n8n-*" }
$marketing | Select-Object name, url, events, active, success_count, failure_count | Format-Table -AutoSize
