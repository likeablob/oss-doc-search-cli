"""Skill installation for coding agents"""

from pathlib import Path

SKILL_TEMPLATE = """---
name: oss-doc-search-cli
description: Search OSS library documentation with local vector embeddings. Use when user asks about library/framework docs, API references, or needs documentation lookup for coding tasks.
---

# oss-doc-search-cli Skill

Search and retrieve documentation from OSS libraries using local vector embeddings.

## Workflow

Two-step workflow for documentation search:

1. **Resolve library**: `ossds resolve <library_name>`
   - Fuzzy match supported (typos, partial names, abbreviations)
   - Returns library ID like `/vercel/next.js`

2. **Query documentation**: `ossds query <library_id> "<search_text>"`
   - Vector similarity search with local embeddings
   - Returns relevant chunks with source URLs

## Commands

| Command | Purpose |
|---------|---------|
| `resolve <name>` | Resolve library name to ID |
| `query <id> "<text>"` | Search documentation |

## Examples

```bash
# Resolve library name (fuzzy match works)
ossds resolve next.js
ossds resolve fasti     # typo → /fastify/fastify

# Query documentation
ossds query /vercel/next.js "app router setup" -k 10
ossds query /fastify/fastify "how to create a plugin"

# Show full content
ossds query /vuejs/vitepress "configuration" --full
```

## Details

- First run auto-downloads manifest
- Missing indexes auto-download on query
- Output includes raw.githubusercontent.com URLs to source files
- Use `-k N` to control result count (default: 8)
- Use `--full` to show complete content instead of preview
"""

AGENT_PATHS = {
    "opencode": ".agents/skills/oss-doc-search-cli",
    "claude-code": ".claude/skills/oss-doc-search-cli",
}


def get_skill_install_targets(
    agents: list[str] | None = None,
    target: Path | None = None,
) -> list[Path]:
    if agents is None:
        agents = ["claude-code"]
    if target:
        return [target]

    targets: list[Path] = []
    cwd = Path.cwd()

    for agent in agents:
        if agent in AGENT_PATHS:
            targets.append(cwd / AGENT_PATHS[agent])

    return targets


def install_skill(target: Path) -> bool:
    try:
        target.mkdir(parents=True, exist_ok=True)
        skill_file = target / "SKILL.md"
        skill_file.write_text(SKILL_TEMPLATE, encoding="utf-8")
        return True
    except Exception:
        return False


def install_skills(
    agents: list[str] | None = None,
    target: Path | None = None,
) -> list[Path]:
    if agents is None:
        agents = ["claude-code"]
    targets = get_skill_install_targets(agents, target)
    installed: list[Path] = []

    for t in targets:
        if install_skill(t):
            installed.append(t)

    return installed
