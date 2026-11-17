<#
APT4989.dll (Jet 4.0 mdb) 압축 및 복구 — Access 엔진(DAO DBEngine.CompactDatabase) 사용, Access 프로그램 불필요.

순서: .ldb(사용 중) 확인 → 임시 파일로 압축 → 테이블별 행 수/정렬 비교
      → (-Commit 일 때만) 원본을 .bak-precompact-<시각> 으로 백업하고 압축본으로 교체

기본은 DRY-RUN: 압축본을 만들어 검증만 하고 지운다. 원본은 그대로.

    powershell -ExecutionPolicy Bypass -File compact_db.ps1             # dry-run (config 의 DB)
    powershell -ExecutionPolicy Bypass -File compact_db.ps1 -Commit     # 실제 교체
    powershell -ExecutionPolicy Bypass -File compact_db.ps1 -Db E:\...\APT4989.dll

- DB 경로/비밀번호는 config.toml + config.local.toml (lib4989) 에서 읽는다. 비밀번호는 출력하지 않음.
- 정렬 방식(CollatingOrder)과 Jet 4.0 형식을 그대로 유지한다.
- 4989 프로그램을 누가 열고 있으면(.ldb 존재) 중단한다.
- UNC(\\서버\공유) DB는 SSH(키 인증) 세션에서 접근이 거부된다 → 데스크톱 세션에서 실행.
#>
param(
    [string]$Db,
    [switch]$Commit
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSCommandPath
$py   = Join-Path $here '.venv\Scripts\python.exe'

Push-Location $here
try {
    if (-not $Db) {
        $Db = & $py -c "from lib4989 import load_config; print(load_config('config.toml').db.path, end='')"
    }
    $pw = & $py -c "from lib4989 import load_config; print(load_config('config.toml').db.password, end='')"
} finally { Pop-Location }
$conn = ";pwd=$pw"

$src = $Db
$ldb = [IO.Path]::ChangeExtension($src, '.ldb')
$ts  = Get-Date -f yyyyMMdd-HHmmss
$tmp = "$src.compact-$ts"
$bak = "$src.bak-precompact-$ts"

if (-not (Test-Path $src)) { throw "DB 없음: $src" }
if (Test-Path $ldb) { Write-Host "중단: $ldb 있음 (누가 4989 를 열고 있음)"; exit 2 }

$eng = New-Object -ComObject DAO.DBEngine.120

function Get-DbInfo([string]$path) {
    $d = $eng.OpenDatabase($path, $false, $true, $conn)   # 읽기 전용
    try {
        $h = [ordered]@{}
        foreach ($t in $d.TableDefs) {
            if ($t.Name -like 'MSys*' -or $t.Name -like '~*') { continue }
            $rs = $d.OpenRecordset("SELECT COUNT(*) FROM [$($t.Name)]")
            $h[$t.Name] = [int]$rs.Fields.Item(0).Value
            $rs.Close()
        }
        @{ counts = $h; collating = $d.CollatingOrder; version = $d.Version }
    } finally { $d.Close() }
}

$before = Get-DbInfo $src
$size0  = (Get-Item $src).Length
Write-Host "원본: $src ($size0 bytes, Jet $($before.version), CollatingOrder=$($before.collating))"

# 압축본도 원본과 같은 정렬 방식으로 (비밀번호는 locale 문자열 뒤에 붙임)
$locale = switch ($before.collating) {
    1033    { ';LANGID=0x0409;CP=1252;COUNTRY=0' }   # dbLangGeneral
    1042    { ';LANGID=0x0412;CP=949;COUNTRY=0' }    # dbLangKorean
    default { $null }
}
if (-not $locale) { Write-Host "중단: 모르는 CollatingOrder $($before.collating)"; exit 2 }

$eng.CompactDatabase($src, $tmp, "$locale$conn", 64, $conn)   # 64 = dbVersion40
$size1 = (Get-Item $tmp).Length
Write-Host "압축본: $size1 bytes ($([math]::Round(100 - 100 * $size1 / $size0, 1))% 감소)"

$after = Get-DbInfo $tmp
$bad = @($before.counts.Keys | Where-Object { $before.counts[$_] -ne $after.counts[$_] }) +
       @($after.counts.Keys  | Where-Object { -not $before.counts.Contains($_) })
foreach ($k in $before.counts.Keys) {
    $mark = if ($before.counts[$k] -ne $after.counts[$k]) { '  <-- 불일치' } else { '' }
    Write-Host ("  {0,-16} {1,8} -> {2,8}{3}" -f $k, $before.counts[$k], $after.counts[$k], $mark)
}
if ($bad.Count -gt 0 -or $after.collating -ne $before.collating) {
    Write-Host "중단: 행 수/정렬 불일치 ($($bad -join ', ')). 원본 유지, 압축본 남겨 둠: $tmp"
    exit 1
}

if (-not $Commit) {
    Remove-Item $tmp
    Write-Host 'DRY-RUN: 검증만 하고 압축본 삭제 (교체하려면 -Commit)'
    exit 0
}

if (Test-Path $ldb) { Write-Host "중단: 압축 중 누가 4989 를 열었음. 원본 유지, 압축본: $tmp"; exit 2 }
Copy-Item $src $bak
Write-Host "백업: $bak"
$old = "$src.precompact-old-$ts"
Rename-Item $src ([IO.Path]::GetFileName($old))
Rename-Item $tmp ([IO.Path]::GetFileName($src))
Remove-Item $old                          # 같은 내용의 백업($bak)이 따로 있음

$final = Get-DbInfo $src
Write-Host "교체 완료: $src ($((Get-Item $src).Length) bytes), MAIN $($final.counts['MAIN'])행"
