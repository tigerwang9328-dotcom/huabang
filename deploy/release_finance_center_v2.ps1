[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z0-9._/-]+$')]
    [string]$ReleaseRef,

    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$ExpectedCommit,

    [Parameter(Mandatory)]
    [ValidatePattern('^/[A-Za-z0-9._/-]+$')]
    [string]$HistoryManifest,

    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9a-fA-F]{64}$')]
    [string]$HistoryManifestSha256,

    [ValidateRange(1, 999999999)]
    [int]$ExpectedHistoryVouchers = 339,

    [ValidateRange(1, 999999999)]
    [int]$ExpectedHistoryEntries = 4596,

    [switch]$Execute,

    [string]$Server = 'xiaohu@100.94.89.49',
    [string]$RemoteReleaseScript = '/srv/huabang-ai-center/deploy/release_finance_center_v2.sh'
)

$arguments = @(
    '--release-ref', $ReleaseRef,
    '--expected-commit', $ExpectedCommit.ToLowerInvariant(),
    '--history-manifest', $HistoryManifest,
    '--history-manifest-sha256', $HistoryManifestSha256.ToLowerInvariant(),
    '--expected-history-vouchers', $ExpectedHistoryVouchers,
    '--expected-history-entries', $ExpectedHistoryEntries
)
if ($Execute) {
    $arguments += '--execute'
}

# Every user-controlled fragment is constrained above.  The Linux script owns
# all mutation logic and will still refuse a run without --execute.
$remoteCommand = (@($RemoteReleaseScript) + $arguments) -join ' '
& ssh -o BatchMode=yes $Server $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "Finance V2 remote release exited with code $LASTEXITCODE."
}
