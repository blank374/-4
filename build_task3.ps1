$ErrorActionPreference = 'Stop'
$compiler = Get-Command g++ -ErrorAction Stop
& $compiler.Source -O3 -DNDEBUG -std=c++17 -Wall -Wextra (Join-Path $PSScriptRoot 'task3_solver.cpp') -o (Join-Path $PSScriptRoot 'task3_solver.exe') -lpsapi -lshell32
if ($LASTEXITCODE -ne 0) { throw 'Task 3 compilation failed.' }
Write-Output 'Built task3_solver.exe. Validate with: python verify_task3_solver.py'
