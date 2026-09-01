$ErrorActionPreference = 'Stop'
$compiler = Get-Command g++ -ErrorAction Stop
$sourcePath = Join-Path $PSScriptRoot 'task2_exact.cpp'
$binaryPath = Join-Path $PSScriptRoot 'task2_exact.exe'
& $compiler.Source -O3 -DNDEBUG -std=c++17 -Wall -Wextra $sourcePath -o $binaryPath -lpsapi -lshell32
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed. Stop a running task2_exact.exe before rebuilding.' }
& $binaryPath --self-test
if ($LASTEXITCODE -ne 0) { throw 'Exactness self-test failed.' }
Write-Output "Built and verified: $binaryPath"
