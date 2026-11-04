# skill-import.ps1 - nhan skill moi tai tu app Claude (Save) vao thu muc Skills
# Chay: bam dup Dong-bo-skill.bat  (hoac: powershell -ExecutionPolicy Bypass -File skill-import.ps1)
# Viec script lam:
#   1. Quet Downloads (mac dinh 72 gio gan day) tim file .md/.skill/.zip tai tu app (ke ca file SKILL.md thuc chat la zip)
#   2. Giai nen dung, doc ten + version (dong 5), kiem tra UTF-8
#   3. Chon ban co version cao nhat cho moi skill; so voi ban hien co trong Skills
#   4. Sao luu ban cu vao Skills\backup\<ten>\, ghi ban moi (UTF-8 khong BOM)
#   5. In version + danh sach dong thay doi (so dong cua ban MOI) va ghi vao last_import.txt
#   6. Chuyen file da xu ly sang Skills\imported\ de khong xu ly lai
# Tham so: -DryRun (chi bao, khong ghi) | -Force (cho phep ghi de bang ban cu hon) | -AddNew (cho phep skill moi)
#          -Hours N (quet N gio gan day) | -KeepDownloads (khong chuyen file) | -SelfTest (tu kiem tra, khong dung file that)
param(
  [string]$Downloads = (Join-Path $env:USERPROFILE 'Downloads'),
  [string]$Root = '',
  [string]$ClaudeSkills = (Join-Path $env:USERPROFILE '.claude\skills'),
  [int]$Hours = 72,
  [switch]$DryRun,
  [switch]$Force,
  [switch]$AddNew,
  [switch]$KeepDownloads,
  [switch]$SelfTest
)
$ErrorActionPreference = 'Stop'
if(-not (Test-Path -LiteralPath $Downloads)){
  try { $Downloads = (New-Object -ComObject Shell.Application).NameSpace('shell:Downloads').Self.Path } catch {}
}
if(-not $Root){ $Root = Split-Path -Parent $MyInvocation.MyCommand.Path }
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding($false) } catch {}
$script:Utf8Strict = New-Object Text.UTF8Encoding($false,$true)
$script:Utf8 = New-Object Text.UTF8Encoding($false)
$script:Log = New-Object Collections.Generic.List[string]

function Say([string]$s){ Write-Host $s; $script:Log.Add($s) }
function LogOnly([string]$s){ $script:Log.Add($s) }

# ---------- doc noi dung tu file tai ve ----------
function Get-Payloads([IO.FileInfo]$f){
  $res = New-Object Collections.Generic.List[object]
  $bytes = [IO.File]::ReadAllBytes($f.FullName)
  if($bytes.Length -ge 4 -and $bytes[0] -eq 0x50 -and $bytes[1] -eq 0x4B){
    $ms = New-Object IO.MemoryStream(,$bytes)
    $zip = $null
    try {
      $zip = New-Object IO.Compression.ZipArchive($ms, [IO.Compression.ZipArchiveMode]::Read)
      foreach($e in $zip.Entries){
        if($e.FullName -eq 'SKILL.md' -or $e.FullName.EndsWith('/SKILL.md')){
          $s = $e.Open(); $o = New-Object IO.MemoryStream
          $s.CopyTo($o); $s.Dispose()
          $res.Add([pscustomobject]@{ File=$f; Entry=$e.FullName; Bytes=$o.ToArray() })
        }
      }
    } catch {
      $res.Add([pscustomobject]@{ File=$f; Entry='(zip loi)'; Bytes=$null })
    } finally {
      if($zip){ $zip.Dispose() }
      $ms.Dispose()
    }
  } else {
    $res.Add([pscustomobject]@{ File=$f; Entry='(van ban)'; Bytes=$bytes })
  }
  return $res.ToArray()
}

function Parse-Skill($payload){
  $r = [pscustomobject]@{ Ok=$false; Err=''; Name=''; Version=''; VerLine=0; Text=''; Body=''; Bytes=$null; File=$payload.File; Entry=$payload.Entry; Time=$null }
  $r.Time = $payload.File.LastWriteTime
  if($payload.File.CreationTime -gt $r.Time){ $r.Time = $payload.File.CreationTime }
  $b = $payload.Bytes
  if($null -eq $b -or $b.Length -lt 200){ $r.Err = 'File rong hoac hong (zip loi)'; return $r }
  if($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF){ $b = [byte[]]($b[3..($b.Length-1)]) }
  try { $text = $script:Utf8Strict.GetString($b) } catch { $r.Err = 'Khong phai UTF-8 hop le'; return $r }
  $lines = $text -split "`n"
  if($lines.Length -lt 6 -or $lines[0].TrimEnd("`r") -ne '---'){ $r.Err = 'Khong co frontmatter (---) o dong 1'; return $r }
  $end = -1
  for($i=1; $i -lt $lines.Length; $i++){ if($lines[$i].TrimEnd("`r") -eq '---'){ $end = $i; break } }
  if($end -lt 0){ $r.Err = 'Frontmatter khong dong (thieu --- thu hai)'; return $r }
  for($i=1; $i -lt $end; $i++){
    $l = $lines[$i].TrimEnd("`r")
    if($l -match '^name:\s*"?([^"]+?)"?\s*$' -and -not $r.Name){ $r.Name = $Matches[1] }
    if($l -match '^\s+version:\s*"?([^"]+?)"?\s*$' -and -not $r.Version){ $r.Version = $Matches[1]; $r.VerLine = $i + 1 }
  }
  if(-not $r.Name){ $r.Err = 'Frontmatter thieu name'; return $r }
  if($r.Name -notmatch '^[a-z0-9][a-z0-9_-]*$'){ $r.Err = "Ten skill la: $($r.Name)"; return $r }
  if(-not $r.Version){ $r.Err = 'Frontmatter thieu metadata.version'; return $r }
  $r.Text = $text
  $r.Body = ($text -replace "`r`n","`n").TrimEnd()
  $r.Bytes = $b
  $r.Ok = $true
  return $r
}

function Ver-Nums([string]$v){
  $p = New-Object Collections.Generic.List[int]
  foreach($m in [regex]::Matches($v,'\d+')){ $p.Add([int]$m.Value) }
  return $p.ToArray()
}
function Ver-Cmp([string]$a,[string]$b){
  $x = Ver-Nums $a; $y = Ver-Nums $b
  $n = [Math]::Max($x.Length,$y.Length)
  for($i=0; $i -lt $n; $i++){
    $p = 0; if($i -lt $x.Length){ $p = $x[$i] }
    $q = 0; if($i -lt $y.Length){ $q = $y[$i] }
    if($p -lt $q){ return -1 }
    if($p -gt $q){ return 1 }
  }
  return 0
}

# ---------- so sanh theo dong ----------
function Get-Hunks([string[]]$a,[string[]]$b){
  $n = $a.Length; $m = $b.Length
  $pre = 0
  while($pre -lt $n -and $pre -lt $m -and ($a[$pre] -ceq $b[$pre])){ $pre++ }
  $suf = 0
  while($suf -lt ($n-$pre) -and $suf -lt ($m-$pre) -and ($a[$n-1-$suf] -ceq $b[$m-1-$suf])){ $suf++ }
  $an = $n - $pre - $suf; $bn = $m - $pre - $suf
  $L = New-Object 'int[,]' ($an+1),($bn+1)
  for($i = $an-1; $i -ge 0; $i--){
    for($j = $bn-1; $j -ge 0; $j--){
      if($a[$pre+$i] -ceq $b[$pre+$j]){ $L[$i,$j] = $L[($i+1),($j+1)] + 1 }
      else {
        $x = $L[($i+1),$j]; $y = $L[$i,($j+1)]
        if($x -ge $y){ $L[$i,$j] = $x } else { $L[$i,$j] = $y }
      }
    }
  }
  $hunks = New-Object Collections.Generic.List[object]
  $i = 0; $j = 0; $cur = $null
  while($i -lt $an -or $j -lt $bn){
    if($i -lt $an -and $j -lt $bn -and ($a[$pre+$i] -ceq $b[$pre+$j])){
      if($cur){ $hunks.Add($cur); $cur = $null }
      $i++; $j++
    } elseif($j -lt $bn -and ($i -ge $an -or $L[$i,($j+1)] -ge $L[($i+1),$j])){
      if(-not $cur){ $cur = [pscustomobject]@{ OldStart=($pre+$i+1); NewStart=($pre+$j+1); Del=(New-Object Collections.Generic.List[string]); Ins=(New-Object Collections.Generic.List[string]) } }
      $cur.Ins.Add($b[$pre+$j]); $j++
    } else {
      if(-not $cur){ $cur = [pscustomobject]@{ OldStart=($pre+$i+1); NewStart=($pre+$j+1); Del=(New-Object Collections.Generic.List[string]); Ins=(New-Object Collections.Generic.List[string]) } }
      $cur.Del.Add($a[$pre+$i]); $i++
    }
  }
  if($cur){ $hunks.Add($cur) }
  return $hunks.ToArray()
}

function Clip([string]$s){ $s = $s.TrimEnd("`r"); if($s.Length -gt 150){ return $s.Substring(0,150) + '...' } return $s }

function Show-Diff([string]$oldBody,[string]$newBody){
  $a = $oldBody -split "`n"; $b = $newBody -split "`n"
  $hunks = @(Get-Hunks $a $b)
  if($hunks.Count -eq 0){ Say '  (khong co dong nao khac)'; return [pscustomobject]@{ Plus=0; Minus=0 } }
  $add = 0; $del = 0; $pos = New-Object Collections.Generic.List[string]
  foreach($h in $hunks){
    $add += $h.Ins.Count; $del += $h.Del.Count
    if($h.Ins.Count -gt 0){
      $s = $h.NewStart; $e = $h.NewStart + $h.Ins.Count - 1
      if($s -eq $e){ $pos.Add("$s") } else { $pos.Add("$s-$e") }
    } else { $pos.Add("(xoa sau dong " + ($h.NewStart-1) + ")") }
  }
  Say ("  Them/doi {0} dong, xoa/thay {1} dong, {2} vung. Vi tri dong trong ban MOI: {3}" -f $add,$del,$hunks.Count,($pos -join ', '))
  $shown = 0; $max = 70
  foreach($h in $hunks){
    $hdr = ""
    if($h.Ins.Count -gt 0){ $hdr = "  Dong moi {0}-{1} (cu: dong {2}, {3} dong)" -f $h.NewStart,($h.NewStart+$h.Ins.Count-1),$h.OldStart,$h.Del.Count }
    else { $hdr = "  Xoa {0} dong (cu: dong {1}), nam sau dong moi {2}" -f $h.Del.Count,$h.OldStart,($h.NewStart-1) }
    $lines = New-Object Collections.Generic.List[string]
    foreach($d in $h.Del){ $lines.Add('    - ' + (Clip $d)) }
    foreach($d in $h.Ins){ $lines.Add('    + ' + (Clip $d)) }
    if($shown -lt $max){ Write-Host $hdr }
    LogOnly $hdr
    foreach($l in $lines){
      if($shown -lt $max){ Write-Host $l; $shown++ }
      LogOnly $l
    }
  }
  if($shown -ge $max){ Write-Host '  ... (con nua, xem day du trong last_import.txt)' }
  return [pscustomobject]@{ Plus=$add; Minus=$del }
}

# ---------- xu ly chinh ----------
function Invoke-Import([string]$Root,[string]$Downloads,[string]$ClaudeSkills,[int]$Hours,[bool]$DryRun,[bool]$Force,[bool]$AddNew,[bool]$Keep){
  $results = New-Object Collections.Generic.List[object]
  if(-not (Test-Path $Downloads)){ throw "Khong thay thu muc Downloads: $Downloads" }
  $cutoff = (Get-Date).AddHours(-$Hours)
  $files = @(Get-ChildItem $Downloads -File -ErrorAction SilentlyContinue | Where-Object {
    $t = $_.LastWriteTime; if($_.CreationTime -gt $t){ $t = $_.CreationTime }
    $t -ge $cutoff -and $_.Length -gt 200 -and $_.Length -lt 5MB -and (@('.md','.skill','.zip') -contains $_.Extension.ToLower())
  })
  Say ("Quet {0}: {1} file ung vien trong {2} gio gan day." -f $Downloads,$files.Count,$Hours)

  $cands = New-Object Collections.Generic.List[object]
  $handled = @{}
  foreach($f in $files){
    $looksSkill = ($f.Name -like 'SKILL*') -or ($f.Extension -ieq '.skill')
    $payloads = @()
    try { $payloads = @(Get-Payloads $f) } catch { Say ("  Khong doc duoc {0}: {1}" -f $f.Name,$_.Exception.Message); continue }
    foreach($p in $payloads){
      $s = Parse-Skill $p
      if($s.Ok){ $cands.Add($s) }
      elseif($looksSkill -or $p.Entry -like '*SKILL.md'){ Say ("  Bo qua {0} [{1}]: {2}" -f $f.Name,$p.Entry,$s.Err) }
    }
  }
  if($cands.Count -eq 0){
    Say 'Khong tim thay file skill nao trong Downloads. Hay bam Save o app (skill can dong bo) roi chay lai.'
    return $results.ToArray()
  }

  $names = @($cands | ForEach-Object { $_.Name } | Select-Object -Unique)
  foreach($name in $names){
    $mine = @($cands | Where-Object { $_.Name -eq $name })
    $best = $null
    foreach($c in $mine){
      if(-not $best){ $best = $c; continue }
      $cmp = Ver-Cmp $c.Version $best.Version
      if($cmp -gt 0 -or ($cmp -eq 0 -and $c.Time -gt $best.Time)){ $best = $c }
    }
    Say ''
    Say ("== {0}: chon {1} (version {2}, dong {3}), tim thay {4} ban ==" -f $name,$best.File.Name,$best.Version,$best.VerLine,$mine.Count)
    if($best.VerLine -ne 5){ Say ("  Luu y: version nam o dong {0}, khong phai dong 5." -f $best.VerLine) }
    foreach($c in $mine){ $handled[$c.File.FullName] = $true }

    $dir = Join-Path $Root $name
    $master = Join-Path $dir 'SKILL.md'
    $rec = [pscustomobject]@{ Name=$name; Action=''; OldVer='-'; NewVer=$best.Version; Plus=0; Minus=0 }
    if(-not (Test-Path $master)){
      if(-not $AddNew){
        Say "  Skill '$name' chua co trong $Root. Them -AddNew neu muon nhan skill moi."
        $rec.Action = 'bo-qua-skill-moi'; $results.Add($rec)
        foreach($c in $mine){ $handled.Remove($c.File.FullName) }
        continue
      }
      if($DryRun){ Say '  [DryRun] se tao skill moi.'; $rec.Action = 'se-tao-moi'; $results.Add($rec); continue }
      New-Item -ItemType Directory -Force $dir | Out-Null
      [IO.File]::WriteAllBytes($master, $best.Bytes)
      Say ("  Da tao skill moi v{0}." -f $best.Version)
      $rec.Action = 'tao-moi'; $results.Add($rec)
      continue
    }

    $curText = $script:Utf8.GetString([IO.File]::ReadAllBytes($master))
    if($curText.Length -gt 0 -and $curText[0] -eq [char]0xFEFF){ $curText = $curText.Substring(1) }
    $curBody = ($curText -replace "`r`n","`n").TrimEnd()
    $curVer = '(khong ro)'
    foreach($l in ($curText -split "`n")){ if($l.TrimEnd("`r") -match '^\s+version:\s*"?([^"]+?)"?\s*$'){ $curVer = $Matches[1]; break } }
    $rec.OldVer = $curVer

    if($best.Body -ceq $curBody){
      Say ("  Da la ban moi nhat (v{0}), khong thay doi gi." -f $curVer)
      $rec.Action = 'da-moi-nhat'; $results.Add($rec); continue
    }
    $cmp = Ver-Cmp $best.Version $curVer
    if($cmp -lt 0 -and -not $Force){
      Say ("  Ban tai ve (v{0}) CU HON ban trong Skills (v{1}). Khong ghi de. Neu chac chan, chay lai voi -Force." -f $best.Version,$curVer)
      $rec.Action = 'bo-qua-ban-cu'; $results.Add($rec)
      foreach($c in $mine){ $handled.Remove($c.File.FullName) }
      continue
    }
    if($cmp -eq 0){ Say '  Canh bao: cung version nhung noi dung khac (co the quen tang version trong app). Van nhan vi app la ban goc.' }
    Say ("  Cap nhat: v{0} -> v{1}" -f $curVer,$best.Version)
    $d = Show-Diff $curBody $best.Body
    $rec.Plus = $d.Plus; $rec.Minus = $d.Minus
    if($DryRun){ Say '  [DryRun] chua ghi gi.'; $rec.Action = 'se-cap-nhat'; $results.Add($rec); continue }

    # sao luu
    $bdir = Join-Path (Join-Path $Root 'backup') $name
    New-Item -ItemType Directory -Force $bdir | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $bfile = Join-Path $bdir ("SKILL_v{0}_{1}.md" -f $curVer,$stamp)
    $k = 1; while(Test-Path $bfile){ $bfile = Join-Path $bdir ("SKILL_v{0}_{1}_{2}.md" -f $curVer,$stamp,$k); $k++ }
    Copy-Item $master $bfile
    Get-ChildItem $bdir -Filter 'SKILL_*.md' | Sort-Object LastWriteTime -Descending | Select-Object -Skip 20 | Remove-Item -Force
    # ghi ban moi + kiem tra lai
    [IO.File]::WriteAllBytes($master, $best.Bytes)
    $chk = $script:Utf8.GetString([IO.File]::ReadAllBytes($master))
    if((($chk -replace "`r`n","`n").TrimEnd()) -cne $best.Body){ throw "Ghi $master xong nhung doc lai khong khop. Ban cu o $bfile" }
    Say ("  Da ghi {0} (UTF-8 khong BOM). Ban cu luu o {1}" -f $master,$bfile)
    # ban sao cho Claude Code (neu thu muc skill cua Claude Code ton tai)
    $cc = Join-Path (Join-Path $ClaudeSkills $name) 'SKILL.md'
    if(Test-Path $cc){ [IO.File]::WriteAllBytes($cc, $best.Bytes); Say "  Da cap nhat ca ban sao cho Claude Code: $cc" }
    $rec.Action = 'da-cap-nhat'; $results.Add($rec)
  }

  # chuyen file da xu ly
  if(-not $DryRun -and -not $Keep){
    $idir = Join-Path $Root 'imported'
    foreach($path in @($handled.Keys)){
      if(-not (Test-Path -LiteralPath $path)){ continue }
      New-Item -ItemType Directory -Force $idir | Out-Null
      $fi = Get-Item -LiteralPath $path
      $dest = Join-Path $idir ((Get-Date -Format 'yyyyMMdd-HHmmss') + '_' + $fi.Name)
      $k = 1; while(Test-Path $dest){ $dest = Join-Path $idir ((Get-Date -Format 'yyyyMMdd-HHmmss') + "_${k}_" + $fi.Name); $k++ }
      Move-Item -LiteralPath $path -Destination $dest
    }
  }
  return $results.ToArray()
}

# ---------- tu kiem tra ----------
function Invoke-SelfTest {
  $t = Join-Path $env:TEMP ('skillsync_test_' + [guid]::NewGuid().ToString('N').Substring(0,8))
  $r = Join-Path $t 'Skills'; $d = Join-Path $t 'Downloads'; $c = Join-Path $t 'claude'
  New-Item -ItemType Directory -Force (Join-Path $r 'test-skill') | Out-Null
  New-Item -ItemType Directory -Force $d | Out-Null
  New-Item -ItemType Directory -Force (Join-Path $c 'test-skill') | Out-Null
  function MkText([string]$ver,[string[]]$body){
    $h = "---`nname: `"test-skill`"`ndescription: `"Thu nghiem`"`nmetadata:`n  version: `"$ver`"`n---`n"
    return $h + (($body -join "`n")) + "`n"
  }
  function MkZip([string]$path,[hashtable]$entries){
    if(Test-Path $path){ Remove-Item $path -Force }
    $fs = [IO.File]::Create($path)
    $z = New-Object IO.Compression.ZipArchive($fs,[IO.Compression.ZipArchiveMode]::Create)
    foreach($k in $entries.Keys){
      $e = $z.CreateEntry($k); $s = $e.Open(); $b = $entries[$k]; $s.Write($b,0,$b.Length); $s.Dispose()
    }
    $z.Dispose(); $fs.Dispose()
  }
  $pad = @(); for($i=1;$i -le 40;$i++){ $pad += "Dong thu $i cua noi dung thu nghiem, co chu tieng Viet: ky thuat tam kim loai." }
  $v1 = MkText '2026.01.01-1' $pad
  $pad2 = $pad.Clone(); $pad2[9] = 'Dong 10 DA SUA'; $pad2 += 'Dong them o cuoi'
  $v2 = MkText '2026.01.02-1' $pad2
  $pad3 = $pad2.Clone(); $pad3[19] = 'Dong 20 sua lan 3'
  $v3 = MkText '2026.01.03-1' $pad3
  $master = Join-Path (Join-Path $r 'test-skill') 'SKILL.md'
  [IO.File]::WriteAllBytes($master, $script:Utf8.GetBytes($v1))
  [IO.File]::WriteAllBytes((Join-Path (Join-Path $c 'test-skill') 'SKILL.md'), $script:Utf8.GetBytes($v1))
  $pass = 0; $fail = 0
  function Check([string]$what,[bool]$ok){ if($ok){ $script:pass++; Write-Host ("  PASS  " + $what) } else { $script:fail++; Write-Host ("  FAIL  " + $what) -ForegroundColor Red } }
  $script:pass = 0; $script:fail = 0
  function Read-M { return $script:Utf8.GetString([IO.File]::ReadAllBytes($master)) }

  Write-Host '--- Ca 1: file SKILL.md thuc chat la zip (bo cuc plugin), version moi hon'
  MkZip (Join-Path $d 'SKILL.md') @{ '.claude-plugin/plugin.json' = $script:Utf8.GetBytes('{"name":"test-skill"}'); 'skills/test-skill/SKILL.md' = $script:Utf8.GetBytes($v2) }
  $res = @(Invoke-Import $r $d $c 72 $false $false $false $false)
  Check 'ban moi duoc ghi' ((Read-M) -ceq $v2)
  Check 'co ban sao luu' ((@(Get-ChildItem (Join-Path (Join-Path $r 'backup') 'test-skill') -Filter 'SKILL_v2026.01.01-1_*.md')).Count -eq 1)
  Check 'ban sao Claude Code duoc cap nhat' (($script:Utf8.GetString([IO.File]::ReadAllBytes((Join-Path (Join-Path $c 'test-skill') 'SKILL.md')))) -ceq $v2)
  Check 'file tai ve da chuyen vao imported' ((-not (Test-Path (Join-Path $d 'SKILL.md'))) -and (@(Get-ChildItem (Join-Path $r 'imported')).Count -eq 1))
  Check 'ket qua = da-cap-nhat, +/- dong dung' (($res.Count -eq 1) -and ($res[0].Action -eq 'da-cap-nhat') -and ($res[0].Plus -eq 3) -and ($res[0].Minus -eq 2))

  Write-Host '--- Ca 2: tai lai dung ban da co'
  MkZip (Join-Path $d 'SKILL (1).md') @{ 'skills/test-skill/SKILL.md' = $script:Utf8.GetBytes($v2) }
  $res = @(Invoke-Import $r $d $c 72 $false $false $false $false)
  Check 'nhan ra da la ban moi nhat' (($res.Count -eq 1) -and ($res[0].Action -eq 'da-moi-nhat'))
  Check 'noi dung khong doi' ((Read-M) -ceq $v2)

  Write-Host '--- Ca 3: ban tai ve CU HON'
  MkZip (Join-Path $d 'test-skill.skill') @{ 'test-skill/SKILL.md' = $script:Utf8.GetBytes($v1) }
  $res = @(Invoke-Import $r $d $c 72 $false $false $false $false)
  Check 'khong ghi de bang ban cu' (($res.Count -eq 1) -and ($res[0].Action -eq 'bo-qua-ban-cu') -and ((Read-M) -ceq $v2))
  Check 'file cu van o Downloads (khong bi chuyen)' (Test-Path (Join-Path $d 'test-skill.skill'))
  Remove-Item (Join-Path $d 'test-skill.skill') -Force

  Write-Host '--- Ca 4: van ban co BOM + nhieu file, chon version cao nhat'
  $bom = $script:Utf8.GetBytes([string][char]0xFEFF + $v3)
  [IO.File]::WriteAllBytes((Join-Path $d 'SKILL (2).md'), $bom)
  MkZip (Join-Path $d 'SKILL (3).md') @{ 'skills/test-skill/SKILL.md' = $script:Utf8.GetBytes($v2) }
  $res = @(Invoke-Import $r $d $c 72 $false $false $false $false)
  Check 'chon v3 va bo BOM' (((Read-M) -ceq $v3) -and ($script:Utf8.GetBytes((Read-M))[0] -eq 0x2D))
  Check 'chi sua dong 20' (($res.Count -eq 1) -and ($res[0].Plus -eq 2) -and ($res[0].Minus -eq 2))

  Write-Host '--- Ca 5: file hong / khong phai skill khong lam script loi'
  [IO.File]::WriteAllBytes((Join-Path $d 'SKILL (4).md'), [byte[]]((0xFF,0xFE,0x00,0x41) * 100))
  [IO.File]::WriteAllText((Join-Path $d 'ghichu.md'), ('khong phai skill ' * 30))
  MkZip (Join-Path $d 'khac.zip') @{ 'a.txt' = $script:Utf8.GetBytes(('xyz ' * 100)) }
  $res = @(Invoke-Import $r $d $c 72 $false $false $false $false)
  Check 'khong co ket qua cap nhat, ban chinh khong doi' (($res.Count -eq 0) -and ((Read-M) -ceq $v3))

  Write-Host '--- Ca 6: -DryRun khong ghi gi'
  Remove-Item (Join-Path $d 'SKILL (4).md') -Force
  $pad4 = $pad3.Clone(); $pad4[0] = 'Dong 1 sua lan 4'
  $v4 = MkText '2026.01.04-1' $pad4
  MkZip (Join-Path $d 'SKILL.md') @{ 'skills/test-skill/SKILL.md' = $script:Utf8.GetBytes($v4) }
  $res = @(Invoke-Import $r $d $c 72 $true $false $false $false)
  Check 'DryRun: ban chinh khong doi, file con o Downloads' (((Read-M) -ceq $v3) -and (Test-Path (Join-Path $d 'SKILL.md')) -and ($res[0].Action -eq 'se-cap-nhat'))

  Write-Host '--- Ca 7: skill moi can -AddNew'
  $other = ($v4 -replace 'test-skill','skill-khac')
  MkZip (Join-Path $d 'skill-khac.skill') @{ 'skill-khac/SKILL.md' = $script:Utf8.GetBytes($other) }
  $res = @(Invoke-Import $r $d $c 72 $false $false $false $false)
  Check 'khong tu y them skill la' ((-not (Test-Path (Join-Path $r 'skill-khac'))) -and (Test-Path (Join-Path $d 'skill-khac.skill')))
  $res = @(Invoke-Import $r $d $c 72 $false $false $true $false)
  Check 'co -AddNew thi tao' (Test-Path (Join-Path (Join-Path $r 'skill-khac') 'SKILL.md'))

  Write-Host ''
  Write-Host ("KET QUA TU KIEM TRA: {0} dat, {1} loi" -f $script:pass,$script:fail)
  Remove-Item $t -Recurse -Force -ErrorAction SilentlyContinue
  if($script:fail -gt 0){ exit 1 }
}

# ---------- main ----------
$sw = [Diagnostics.Stopwatch]::StartNew()
if($SelfTest){ Invoke-SelfTest; return }
Say ("skill-import  {0}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
$res = @(Invoke-Import $Root $Downloads $ClaudeSkills $Hours ([bool]$DryRun) ([bool]$Force) ([bool]$AddNew) ([bool]$KeepDownloads))
Say ''
Say '=== TOM TAT ==='
foreach($x in $res){
  switch($x.Action){
    'da-cap-nhat' { Say ("  {0}: DA CAP NHAT v{1} -> v{2} (+{3} / -{4} dong)" -f $x.Name,$x.OldVer,$x.NewVer,$x.Plus,$x.Minus) }
    'tao-moi'     { Say ("  {0}: DA TAO MOI v{1}" -f $x.Name,$x.NewVer) }
    'da-moi-nhat' { Say ("  {0}: da la ban moi nhat (v{1})" -f $x.Name,$x.OldVer) }
    'bo-qua-ban-cu' { Say ("  {0}: bo qua, ban tai ve cu hon (v{1} < v{2})" -f $x.Name,$x.NewVer,$x.OldVer) }
    default       { Say ("  {0}: {1}" -f $x.Name,$x.Action) }
  }
}
Say ("Thoi gian chay: {0:N1} giay" -f $sw.Elapsed.TotalSeconds)
if(-not $DryRun){
  try { [IO.File]::WriteAllText((Join-Path $Root 'last_import.txt'), ($script:Log -join "`r`n"), (New-Object Text.UTF8Encoding($true))) } catch {}
}
