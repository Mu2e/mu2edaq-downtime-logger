"""Windows PowerShell launch-script coverage.

Added in the windows-compat sweep. Locks in the .sh/.ps1 parity for the
control scripts and parse-checks the PowerShell ports. (The logfile-rotation
behaviour on Windows is covered in test_detector_logfile.py.)
"""
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent

SCRIPT_STEMS = [
    "bootstrap",
    "start-mu2edaq-downtime-logger",
    "stop-mu2edaq-downtime-logger",
]

PWSH = shutil.which("pwsh") or shutil.which("powershell")


def test_scripts_have_both_forms():
    for stem in SCRIPT_STEMS:
        assert (REPO / f"{stem}.sh").is_file(), f"missing bash script: {stem}.sh"
        assert (REPO / f"{stem}.ps1").is_file(), f"missing PowerShell port: {stem}.ps1"


@pytest.mark.skipif(not PWSH, reason="PowerShell not available")
@pytest.mark.parametrize("stem", SCRIPT_STEMS)
def test_powershell_scripts_parse(stem):
    path = (REPO / f"{stem}.ps1").as_posix()
    code = (
        "$e=$null;"
        f"[System.Management.Automation.Language.Parser]::ParseFile('{path}',[ref]$null,[ref]$e)|Out-Null;"
        "if($e){$e|ForEach-Object{Write-Error $_};exit 1}else{exit 0}"
    )
    result = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-Command", code],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
