# Rachel-v2 Codex Skill Installation

Release: `Rachel-v2-20260721_142758-codex-skill`

## 1. Prepare The Environment

```powershell
conda env create -f environment.yml
conda activate rachel-v2
```

If the environment already exists, activate it and continue.

## 2. Install The Skill

Use `$CODEX_HOME` when it is configured. Otherwise Codex defaults to
`$HOME\.codex` on Windows.

```powershell
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
$SkillTarget = Join-Path $CodexHome 'skills\Rachel'
New-Item -ItemType Directory -Force -Path (Split-Path $SkillTarget) | Out-Null
Copy-Item -Recurse -Force '.\Rachel' $SkillTarget
```

Restart Codex or open a new task so the Skill catalog is refreshed.

## 3. Verify The Extracted Release

From this release root:

```powershell
conda activate rachel-v2
python VERIFY_RELEASE.py
```

Expected output is JSON containing `"ok": true`. The verifier checks file
hashes, runtime imports, prompt setup, reaction-site disclosure, validation
modules, terminal allowlist loading, and the terminal-audit parser.

This release is verified on Windows with Python 3.11 and RDKit. Other operating
systems are not claimed as verified by this package.
