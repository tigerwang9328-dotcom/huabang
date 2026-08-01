param(
    [Parameter(Mandatory = $true)][string]$ServerInstance,
    [Parameter(Mandatory = $true)][string]$AccountSetsJson,
    [Parameter(Mandatory = $true)][string]$OutputRoot
)

$ErrorActionPreference = 'Stop'
$accountSets = Get-Content -LiteralPath $AccountSetsJson -Raw | ConvertFrom-Json
$utf8 = New-Object System.Text.UTF8Encoding($false)
$tables = [ordered]@{
    accounts = 't_Account'
    vouchers = 't_Voucher'
    voucher_entries = 't_VoucherEntry'
    balances = 't_Balance'
    departments = 't_Department'
    employees = 't_Base_Emp'
    suppliers = 't_Supplier'
    currencies = 't_Currency'
    aux_items = 't_Item'
}

function Convert-DbValue($value) {
    if ($value -is [DBNull]) { return $null }
    if ($value -is [DateTime]) { return $value.ToString('o') }
    if ($value -is [byte[]]) { return [Convert]::ToBase64String($value) }
    return $value
}

function Export-JsonLines([string]$database, [string]$table, [string]$path) {
    $builder = New-Object System.Data.SqlClient.SqlConnectionStringBuilder
    $builder['Data Source'] = $ServerInstance
    $builder['Initial Catalog'] = $database
    $builder['Integrated Security'] = $true
    $builder['Application Name'] = 'Huabang Kingdee ReadOnly Extractor'
    $connection = New-Object System.Data.SqlClient.SqlConnection($builder.ConnectionString)
    $connection.Open()
    try {
        $command = $connection.CreateCommand()
        $command.CommandTimeout = 0
        $command.CommandText = "SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED; SELECT * FROM dbo.[$table]"
        $reader = $command.ExecuteReader()
        $writer = New-Object System.IO.StreamWriter($path, $false, $utf8)
        $count = 0
        try {
            while ($reader.Read()) {
                $row = [ordered]@{}
                for ($index = 0; $index -lt $reader.FieldCount; $index++) {
                    $row[$reader.GetName($index)] = Convert-DbValue $reader.GetValue($index)
                }
                $writer.WriteLine(($row | ConvertTo-Json -Compress -Depth 4))
                $count++
            }
        } finally {
            $writer.Dispose()
            $reader.Dispose()
        }
        return $count
    } finally {
        $connection.Dispose()
    }
}

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$manifest = [ordered]@{
    format_version = 1
    run_id = "K3IMPORT_$((Get-Date).ToString('yyyyMMdd_HHmmss'))"
    generated_at = (Get-Date).ToString('o')
    account_sets = @()
    files = @()
}

foreach ($accountSet in $accountSets) {
    if ($accountSet.classification -ne 'official') { continue }
    $database = [string]$accountSet.restored_database
    $databaseDir = Join-Path $OutputRoot $accountSet.database
    New-Item -ItemType Directory -Path $databaseDir -Force | Out-Null
    $tablePaths = [ordered]@{}
    foreach ($entry in $tables.GetEnumerator()) {
        $relativePath = "$($accountSet.database)/$($entry.Key).jsonl"
        $absolutePath = Join-Path $OutputRoot $relativePath
        $rows = Export-JsonLines $database $entry.Value $absolutePath
        $sha256 = (Get-FileHash -LiteralPath $absolutePath -Algorithm SHA256).Hash.ToLowerInvariant()
        $manifest.files += [ordered]@{ path = $relativePath; sha256 = $sha256; rows = $rows }
        $tablePaths[$entry.Key] = $relativePath
    }
    $manifest.account_sets += [ordered]@{
        database = [string]$accountSet.database
        restored_database = $database
        classification = 'official'
        company_name = [string]$accountSet.company_name
        short_name = [string]$accountSet.short_name
        start_period = [string]$accountSet.start_period
        current_period = [string]$accountSet.current_period
        backup_file = [string]$accountSet.backup_file
        backup_sha256 = [string]$accountSet.backup_sha256
        tables = $tablePaths
    }
}

$manifestPath = Join-Path $OutputRoot 'manifest.json'
[IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 8), $utf8)
$manifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "Manifest: $manifestPath"
Write-Host "SHA-256: $manifestHash"
