@echo off
rem Sleepy Shell standalone launcher.
rem Edit PYTHON below to a Python that has PySide6 installed
rem (the same Python that runs Sleepy Queue works).
set PYTHON=C:\Python312\python.exe
if not exist "%PYTHON%" set PYTHON=python
"%PYTHON%" "%~dp0standalone.py" %*
