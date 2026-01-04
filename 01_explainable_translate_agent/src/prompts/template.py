"""
Prompt Template Loader - Load and render prompt templates from markdown files
"""

import os
import re
import yaml
from typing import Dict, Any, Optional, List
from functools import lru_cache
from pathlib import Path


class PromptTemplate:
    """
    A prompt template loaded from a markdown file.

    Supports:
    - YAML frontmatter for metadata
    - Jinja2-style variable substitution {{ variable }}
    - Section extraction via headers (## Section)
    """

    def __init__(self, content: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Initialize a prompt template.

        Args:
            content: Template content (may include frontmatter)
            metadata: Optional pre-parsed metadata
        """
        self.raw_content = content
        self._metadata = metadata
        self._content = None
        self._parse()

    def _parse(self):
        """Parse frontmatter and content"""
        if self._metadata is not None:
            self._content = self.raw_content
            return

        # Check for YAML frontmatter
        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n'
        match = re.match(frontmatter_pattern, self.raw_content, re.DOTALL)

        if match:
            frontmatter = match.group(1)
            self._metadata = yaml.safe_load(frontmatter) or {}
            self._content = self.raw_content[match.end():]
        else:
            self._metadata = {}
            self._content = self.raw_content

    @property
    def metadata(self) -> Dict[str, Any]:
        """Get template metadata from frontmatter"""
        return self._metadata

    @property
    def content(self) -> str:
        """Get template content (without frontmatter)"""
        return self._content

    def render(self, **kwargs) -> str:
        """
        Render template with variable substitution.

        Args:
            **kwargs: Variables to substitute in the template

        Returns:
            Rendered template string
        """
        result = self._content

        # Simple {{ variable }} substitution
        for key, value in kwargs.items():
            # Support {{ key }} and {{key}} formats
            result = re.sub(
                rf'\{{\{{\s*{key}\s*\}}\}}',
                str(value),
                result
            )

        return result

    def get_section(self, header: str) -> Optional[str]:
        """
        Extract a section by its header.

        Args:
            header: Section header text (without # prefix)

        Returns:
            Section content or None if not found
        """
        # Match markdown headers (##, ###, etc.)
        pattern = rf'^(#+)\s*{re.escape(header)}\s*\n(.*?)(?=\n#+\s|\Z)'
        match = re.search(pattern, self._content, re.MULTILINE | re.DOTALL)

        if match:
            return match.group(2).strip()
        return None

    def get_all_sections(self) -> Dict[str, str]:
        """
        Extract all sections as a dictionary.

        Returns:
            Dict mapping header text to section content
        """
        sections = {}
        pattern = r'^(#+)\s*(.+?)\s*\n(.*?)(?=\n#+\s|\Z)'

        for match in re.finditer(pattern, self._content, re.MULTILINE | re.DOTALL):
            header = match.group(2).strip()
            content = match.group(3).strip()
            sections[header] = content

        return sections


class PromptTemplateLoader:
    """
    Loader for prompt templates from the prompts directory.

    Usage:
        loader = PromptTemplateLoader()
        template = loader.load("translator")
        prompt = template.render(source_text="...", target_lang="en-rUS")
    """

    def __init__(self, prompts_dir: Optional[str] = None):
        """
        Initialize the template loader.

        Args:
            prompts_dir: Path to prompts directory.
                         Defaults to src/prompts/ relative to this file.
        """
        if prompts_dir is None:
            self.prompts_dir = Path(__file__).parent
        else:
            self.prompts_dir = Path(prompts_dir)

    @lru_cache(maxsize=32)
    def load(self, name: str) -> PromptTemplate:
        """
        Load a prompt template by name.

        Args:
            name: Template name (without .md extension)

        Returns:
            PromptTemplate instance

        Raises:
            FileNotFoundError: If template file not found
        """
        # Try with and without .md extension
        candidates = [
            self.prompts_dir / f"{name}.md",
            self.prompts_dir / name,
            self.prompts_dir / f"{name}.txt"
        ]

        for path in candidates:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                return PromptTemplate(content)

        raise FileNotFoundError(
            f"Prompt template '{name}' not found. "
            f"Searched in: {self.prompts_dir}"
        )

    def load_skill(self, skill_name: str) -> PromptTemplate:
        """
        Load a SKILL.md from the skills directory.

        Args:
            skill_name: Skill directory name (e.g., "translator")

        Returns:
            PromptTemplate instance from skills/<skill_name>/SKILL.md
        """
        # Skills are in the skills/ directory at project root
        base_dir = self.prompts_dir.parent.parent  # src -> project root
        skill_path = base_dir / "skills" / skill_name / "SKILL.md"

        if not skill_path.exists():
            raise FileNotFoundError(
                f"Skill '{skill_name}' not found at: {skill_path}"
            )

        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()
        return PromptTemplate(content)

    def load_with_references(
        self,
        name: str,
        include_references: bool = True
    ) -> str:
        """
        Load a template and optionally include referenced files.

        Args:
            name: Template name
            include_references: Whether to inline referenced files

        Returns:
            Complete prompt string with references included
        """
        template = self.load(name)
        content = template.content

        if include_references and "references" in template.metadata:
            refs = template.metadata["references"]
            ref_content = []

            for ref in refs:
                ref_path = self.prompts_dir / ref
                if ref_path.exists():
                    with open(ref_path, "r", encoding="utf-8") as f:
                        ref_content.append(f"## Reference: {ref}\n\n{f.read()}")

            if ref_content:
                content = content + "\n\n" + "\n\n".join(ref_content)

        return content

    def list_templates(self) -> List[str]:
        """List all available prompt templates"""
        templates = []
        for path in self.prompts_dir.glob("*.md"):
            templates.append(path.stem)
        return sorted(templates)

    def clear_cache(self):
        """Clear the template cache"""
        self.load.cache_clear()


# Singleton instance
_default_loader: Optional[PromptTemplateLoader] = None


def get_template_loader(prompts_dir: Optional[str] = None) -> PromptTemplateLoader:
    """Get or create the default template loader singleton"""
    global _default_loader
    if _default_loader is None:
        _default_loader = PromptTemplateLoader(prompts_dir)
    return _default_loader


def load_prompt(name: str, **kwargs) -> str:
    """
    Convenience function to load and render a prompt template.

    Args:
        name: Template name
        **kwargs: Variables to substitute

    Returns:
        Rendered prompt string
    """
    loader = get_template_loader()
    template = loader.load(name)
    return template.render(**kwargs)
