---
description: Initialize a Git repository with an initial commit
---


<!-- Extension: git -->
<!-- Config: .specify/extensions/git/ -->
# Initialize Git Repository

Initialize a Git repository in the current project directory if one does not already exist.

## Execution

Run the appropriate script from the project root:

- **Bash**: `.specify/extensions/git/scripts/bash/initialize-repo.sh`
- **PowerShell**: `.specify/extensions/git/scripts/powershell/initialize-repo.ps1`

If the extension scripts are not found, fall back to:
- **Bash**: `git init && git add .specify .github README.md && git commit -m "Initialize repository for Spec Kit"`
- **PowerShell**: `git init; git add .specify .github README.md; git commit -m "Initialize repository for Spec Kit"`

If one or more fallback paths do not exist, stage only the existing paths. Do not use `git add .` in fallback mode.

The script handles all checks internally:
- Skips if Git is not available
- Skips if already inside a Git repository
- Runs `git init`, stages only scoped initialization files, and creates an initial commit message

## Customization

Replace the script to add project-specific Git initialization steps:
- Custom `.gitignore` templates
- Default branch naming (`git config init.defaultBranch`)
- Git LFS setup
- Git hooks installation
- Commit signing configuration
- Git Flow initialization

## Output

On success:
- `✓ Git repository initialized`

## Graceful Degradation

If Git is not installed:
- Warn the user
- Skip repository initialization
- The project continues to function without Git (specs can still be created under `specs/`)

If Git is installed but `git init`, scoped `git add`, or `git commit` fails:
- Surface the error to the user
- Stop this command rather than continuing with a partially initialized repository