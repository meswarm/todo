"""Skill loading for prompt composition."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    name: str
    description: str
    content: str
    path: Path


def load_system_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"System prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not match:
        return {}, text
    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        frontmatter = {}
    return frontmatter, match.group(2)


def load_skill(skill_dir: Path) -> Skill | None:
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return None
    raw = skill_file.read_text(encoding="utf-8")
    frontmatter, content = _parse_frontmatter(raw)
    return Skill(
        name=frontmatter.get("name", skill_dir.name),
        description=frontmatter.get("description", ""),
        content=content.strip(),
        path=skill_dir,
    )


def load_skills_from_dir(skills_dir: Path) -> list[Skill]:
    path = Path(skills_dir)
    if not path.exists() or not path.is_dir():
        return []

    skills: list[Skill] = []
    for item in sorted(path.iterdir()):
        if not item.is_dir():
            continue
        skill = load_skill(item)
        if skill:
            skills.append(skill)
    return skills


def format_skills_for_prompt(skills: list[Skill]) -> str:
    if not skills:
        return ""

    lines: list[str] = ["# Skills", ""]
    for skill in skills:
        lines.append(f"## {skill.name}")
        if skill.description:
            lines.append(skill.description)
        if skill.content:
            lines.append("")
            lines.append(skill.content)
        lines.append("")
    return "\n".join(lines).strip()


def build_prompt_with_skills(system_prompt: str, skills: list[Skill]) -> str:
    if not skills:
        return system_prompt
    return f"{system_prompt}\n\n{format_skills_for_prompt(skills)}"

