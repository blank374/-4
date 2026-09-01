$ErrorActionPreference = 'Stop'
$compiler = Get-Command g++ -ErrorAction Stop
& $compiler.Source -O3 -DNDEBUG -std=c++17 -Wall -Wextra (Join-Path $PSScriptRoot 'task4_solver.cpp') -o (Join-Path $PSScriptRoot 'task4_solver.exe') -lpsapi -lshell32
if ($LASTEXITCODE -ne 0) { throw 'Task 4 compilation failed.' }
Write-Output 'Built task4_solver.exe. Validate with: python verify_task4_solver.py'
