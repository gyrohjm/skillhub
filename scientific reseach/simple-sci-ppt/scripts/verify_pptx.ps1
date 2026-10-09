param(
  [Parameter(Mandatory=$true)]
  [string]$Pptx,

  [string]$PreviewDir = "",

  [int]$ExpectedSlides = 0
)

$ErrorActionPreference = "Stop"
$resolved = Resolve-Path -LiteralPath $Pptx
$pptPath = $resolved.Path
if (-not $PreviewDir) {
  $PreviewDir = Join-Path (Split-Path -Parent $pptPath) "preview_$([IO.Path]::GetFileNameWithoutExtension($pptPath))"
}
New-Item -ItemType Directory -Force -Path $PreviewDir | Out-Null

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($pptPath)
try {
  $slides = @($zip.Entries | Where-Object { $_.FullName -match '^ppt/slides/slide\d+\.xml$' }).Count
  $emptyMedia = @($zip.Entries | Where-Object { $_.FullName -match '^ppt/media/.+' -and $_.Length -eq 0 }).Count
  $mediaFiles = @($zip.Entries | Where-Object { $_.FullName -match '^ppt/media/.+' }).Count
} finally {
  $zip.Dispose()
}

if ($ExpectedSlides -gt 0 -and $slides -ne $ExpectedSlides) {
  throw "Expected $ExpectedSlides slides, found $slides"
}
if ($emptyMedia -ne 0) {
  throw "Found $emptyMedia empty media files"
}

$pp = $null
$pres = $null
try {
  $pp = New-Object -ComObject PowerPoint.Application
  $pres = $pp.Presentations.Open($pptPath, $true, $false, $false)
  $openedSlides = $pres.Slides.Count
  $pres.Export($PreviewDir, "PNG", 1280, 720)
  $pres.Close()
  $pp.Quit()
} finally {
  if ($pres -ne $null) { [System.Runtime.Interopservices.Marshal]::ReleaseComObject($pres) | Out-Null }
  if ($pp -ne $null) { [System.Runtime.Interopservices.Marshal]::ReleaseComObject($pp) | Out-Null }
}

[pscustomobject]@{
  Pptx = $pptPath
  SlidesInPackage = $slides
  SlidesOpened = $openedSlides
  MediaFiles = $mediaFiles
  EmptyMediaFiles = $emptyMedia
  PreviewDir = (Resolve-Path -LiteralPath $PreviewDir).Path
} | ConvertTo-Json -Depth 3
