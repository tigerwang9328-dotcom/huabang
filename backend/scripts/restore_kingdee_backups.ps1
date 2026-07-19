param(
    [Parameter(Mandatory = $true)][string]$ResultRoot,
    [string]$ServerInstance = '.\K3MIGRATION',
    [string]$ReportPath
)

$ErrorActionPreference = 'Stop'

function Quote-SqlLiteral([string]$value) {
    return "N'$($value.Replace("'", "''"))'"
}

function Quote-SqlIdentifier([string]$value) {
    return "[$($value.Replace(']', ']]'))]"
}

function Invoke-SqlTable([string]$database, [string]$sql) {
    $builder = New-Object System.Data.SqlClient.SqlConnectionStringBuilder
    $builder['Data Source'] = $ServerInstance
    $builder['Initial Catalog'] = $database
    $builder['Integrated Security'] = $true
    $builder['Application Name'] = 'Huabang Kingdee Isolated Restore'
    $connection = New-Object System.Data.SqlClient.SqlConnection($builder.ConnectionString)
    $connection.Open()
    try {
        $command = $connection.CreateCommand()
        $command.CommandTimeout = 0
        $command.CommandText = $sql
        $adapter = New-Object System.Data.SqlClient.SqlDataAdapter($command)
        $table = New-Object System.Data.DataTable
        [void]$adapter.Fill($table)
        return ,$table
    } finally {
        $connection.Dispose()
    }
}

function Invoke-SqlNonQuery([string]$database, [string]$sql) {
    $builder = New-Object System.Data.SqlClient.SqlConnectionStringBuilder
    $builder['Data Source'] = $ServerInstance
    $builder['Initial Catalog'] = $database
    $builder['Integrated Security'] = $true
    $builder['Application Name'] = 'Huabang Kingdee Isolated Restore'
    $connection = New-Object System.Data.SqlClient.SqlConnection($builder.ConnectionString)
    $connection.Open()
    try {
        $command = $connection.CreateCommand()
        $command.CommandTimeout = 0
        $command.CommandText = $sql
        [void]$command.ExecuteNonQuery()
    } finally {
        $connection.Dispose()
    }
}

$manifestPath = Join-Path $ResultRoot 'manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Manifest not found: $manifestPath"
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$dataPath = [string](Invoke-SqlTable 'master' "SELECT CONVERT(nvarchar(4000), SERVERPROPERTY('InstanceDefaultDataPath')) AS data_path").Rows[0].data_path
$report = [ordered]@{
    generated_at = (Get-Date).ToString('o')
    server_instance = $ServerInstance
    source_manifest = $manifestPath
    databases = @()
    errors = @()
}

foreach ($databaseItem in $manifest.databases) {
    $sourceDatabase = [string]$databaseItem.database
    $backupPath = Join-Path $ResultRoot "databases\$sourceDatabase\backup\$sourceDatabase.bak"
    $restoredDatabase = "K3RESTORE_$sourceDatabase"
    $entry = [ordered]@{
        source_database = $sourceDatabase
        restored_database = $restoredDatabase
        backup_path = $backupPath
        expected_sha256 = [string]$databaseItem.backup.sha256
        actual_sha256 = $null
        header = $null
        files = @()
        verify_status = 'pending'
        restore_status = 'pending'
        read_only = $false
        error = $null
    }
    try {
        if (-not (Test-Path -LiteralPath $backupPath)) {
            throw "Backup not found: $backupPath"
        }
        $entry.actual_sha256 = (Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($entry.actual_sha256 -ne $entry.expected_sha256.ToLowerInvariant()) {
            throw "Backup SHA-256 mismatch for $sourceDatabase"
        }
        $backupLiteral = Quote-SqlLiteral $backupPath
        $header = Invoke-SqlTable 'master' "RESTORE HEADERONLY FROM DISK = $backupLiteral"
        $entry.header = [ordered]@{
            database_name = [string]$header.Rows[0].DatabaseName
            backup_type = [int]$header.Rows[0].BackupType
            backup_start_date = ([datetime]$header.Rows[0].BackupStartDate).ToString('o')
            backup_finish_date = ([datetime]$header.Rows[0].BackupFinishDate).ToString('o')
            database_version = [int]$header.Rows[0].DatabaseVersion
            compressed = [bool]$header.Rows[0].Compressed
        }
        $fileList = Invoke-SqlTable 'master' "RESTORE FILELISTONLY FROM DISK = $backupLiteral"
        $moveClauses = @()
        $dataIndex = 0
        $logIndex = 0
        foreach ($file in $fileList.Rows) {
            $logicalName = [string]$file.LogicalName
            $type = [string]$file.Type
            if ($type -eq 'L') {
                $logIndex++
                $targetFile = Join-Path $dataPath "$restoredDatabase`_log$logIndex.ldf"
            } else {
                $dataIndex++
                $targetFile = Join-Path $dataPath "$restoredDatabase`_data$dataIndex.mdf"
            }
            $moveClauses += "MOVE $(Quote-SqlLiteral $logicalName) TO $(Quote-SqlLiteral $targetFile)"
            $entry.files += [ordered]@{ logical_name = $logicalName; type = $type; target_path = $targetFile }
        }
        Invoke-SqlNonQuery 'master' "RESTORE VERIFYONLY FROM DISK = $backupLiteral WITH CHECKSUM"
        $entry.verify_status = 'verified'
        $exists = [int](Invoke-SqlTable 'master' "SELECT COUNT(*) AS value FROM sys.databases WHERE name = $(Quote-SqlLiteral $restoredDatabase)").Rows[0].value
        if ($exists -gt 0) {
            $state = Invoke-SqlTable 'master' "SELECT is_read_only, state_desc FROM sys.databases WHERE name = $(Quote-SqlLiteral $restoredDatabase)"
            if (-not [bool]$state.Rows[0].is_read_only -or [string]$state.Rows[0].state_desc -ne 'ONLINE') {
                throw "Existing restore database is not an online read-only database: $restoredDatabase"
            }
            $entry.restore_status = 'already_restored'
            $entry.read_only = $true
        } else {
            $restoreSql = "RESTORE DATABASE $(Quote-SqlIdentifier $restoredDatabase) FROM DISK = $backupLiteral WITH CHECKSUM, RECOVERY, " + ($moveClauses -join ', ')
            Invoke-SqlNonQuery 'master' $restoreSql
            Invoke-SqlNonQuery 'master' "ALTER DATABASE $(Quote-SqlIdentifier $restoredDatabase) SET READ_ONLY WITH ROLLBACK IMMEDIATE"
            $state = Invoke-SqlTable 'master' "SELECT is_read_only, state_desc FROM sys.databases WHERE name = $(Quote-SqlLiteral $restoredDatabase)"
            $entry.restore_status = if ([string]$state.Rows[0].state_desc -eq 'ONLINE') { 'restored' } else { 'failed' }
            $entry.read_only = [bool]$state.Rows[0].is_read_only
        }
    } catch {
        $entry.verify_status = if ($entry.verify_status -eq 'verified') { 'verified' } else { 'failed' }
        $entry.restore_status = 'failed'
        $entry.error = $_.Exception.Message
        $report.errors += [ordered]@{ database = $sourceDatabase; error = $_.Exception.Message }
    }
    $report.databases += $entry
}

if (-not $ReportPath) {
    $ReportPath = Join-Path $ResultRoot 'local_restore_report.json'
}
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($ReportPath, ($report | ConvertTo-Json -Depth 8), $utf8)
Write-Host "Restore report: $ReportPath"
if ($report.errors.Count -gt 0) {
    throw "$($report.errors.Count) database restore operation(s) failed. See $ReportPath"
}
