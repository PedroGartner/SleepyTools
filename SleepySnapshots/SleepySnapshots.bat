@echo off
rem Snapshot Browser outside Nuke.
rem Uses the Python that ships with Nuke (it includes PySide6).
rem Change NUKE_PYTHON if your Nuke lives somewhere else, or point it at any
rem Python with PySide6 installed.

set "NUKE_PYTHON=C:\Program Files\Nuke17.0v1\python.exe"

cd /d "%~dp0"
"%NUKE_PYTHON%" -m snapbrowser %*
