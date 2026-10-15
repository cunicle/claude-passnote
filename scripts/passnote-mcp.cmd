@echo off
rem Starts the passnote MCP server with the first Python 3.9+ it finds: %PASSNOTE_PYTHON%, then python3, python, py.
rem The plugin's MCP command is ${CLAUDE_PLUGIN_ROOT}/scripts/passnote-mcp: on Windows this file runs (found through
rem PATHEXT), on macOS and Linux passnote-mcp next to it does the same. The "python3" and "python" of the Microsoft Store
rem aliases fail the version check and are skipped; "call" also runs .bat/.cmd shims (pyenv-win) and comes back.
rem Nothing may be written to stdout before the server starts.
setlocal
for %%P in ("%PASSNOTE_PYTHON%" python3 python py) do (
  if not "%%~P"=="" (
    call "%%~P" -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>nul && (
      call "%%~P" "%~dp0mcp_server.py"
      exit /b
    )
  )
)
echo passnote: no Python 3.9+ found (tried %%PASSNOTE_PYTHON%%, python3, python, py); set PASSNOTE_PYTHON to one 1>&2
exit /b 1
