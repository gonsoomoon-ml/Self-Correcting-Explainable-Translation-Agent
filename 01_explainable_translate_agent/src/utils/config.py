"""
Configuration Loader - Load YAML configuration files
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from functools import lru_cache


class ConfigLoader:
    """
    Loader for YAML configuration files.

    Usage:
        config = ConfigLoader()
        languages = config.load("languages")
        thresholds = config.load("thresholds")
    """

    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize the config loader.

        Args:
            config_dir: Path to config directory.
                        Defaults to config/ at project root.
        """
        if config_dir is None:
            # Default: 01_explainable_translate_agent/config/
            base_dir = Path(__file__).parent.parent.parent
            self.config_dir = base_dir / "config"
        else:
            self.config_dir = Path(config_dir)

    @lru_cache(maxsize=32)
    def load(self, name: str) -> Dict[str, Any]:
        """
        Load a configuration file by name.

        Args:
            name: Config file name (without .yaml extension)

        Returns:
            Parsed configuration dict

        Raises:
            FileNotFoundError: If config file not found
        """
        candidates = [
            self.config_dir / f"{name}.yaml",
            self.config_dir / f"{name}.yml",
            self.config_dir / name,
        ]

        for path in candidates:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f)

        raise FileNotFoundError(
            f"Config file '{name}' not found in {self.config_dir}"
        )

    def load_risk_profile(self, country_code: str) -> Dict[str, Any]:
        """
        Load a country-specific risk profile.

        Args:
            country_code: Country code (e.g., "US", "EU", "CN")

        Returns:
            Risk profile configuration
        """
        # risk_profiles are in data/ (not config/) - they're knowledge, not settings
        data_dir = self.config_dir.parent / "data"
        profile_dir = data_dir / "risk_profiles"
        candidates = [
            profile_dir / f"{country_code}.yaml",
            profile_dir / f"{country_code}.yml",
            profile_dir / "DEFAULT.yaml",
        ]

        for path in candidates:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f)

        # Return minimal default if no profile found
        return {
            "profile": {
                "country_code": country_code,
                "regulatory_strictness": "medium"
            },
            "prohibited_terms": [],
            "required_disclaimers": {}
        }

    def list_risk_profiles(self) -> List[str]:
        """List available risk profile country codes"""
        data_dir = self.config_dir.parent / "data"
        profile_dir = data_dir / "risk_profiles"
        if not profile_dir.exists():
            return []

        profiles = []
        for path in profile_dir.glob("*.yaml"):
            profiles.append(path.stem)
        for path in profile_dir.glob("*.yml"):
            profiles.append(path.stem)

        return sorted(set(profiles))

    def load_glossary(
        self,
        product: str,
        target_lang: str
    ) -> Dict[str, str]:
        """
        Load a product-specific glossary for a target language.

        Args:
            product: Product identifier (e.g., "abc_cloud")
            target_lang: Target language code (e.g., "en", "en-rUS", "ja")

        Returns:
            Glossary dict mapping source terms to target terms
        """
        data_dir = self.config_dir.parent / "data"
        glossary_dir = data_dir / "glossaries" / product

        # Normalize language code: "en-rUS" → "en"
        base_lang = target_lang.split("-")[0]

        candidates = [
            glossary_dir / f"{target_lang}.yaml",  # exact match (en-rUS.yaml)
            glossary_dir / f"{target_lang}.yml",
            glossary_dir / f"{base_lang}.yaml",    # base language (en.yaml)
            glossary_dir / f"{base_lang}.yml",
        ]

        for path in candidates:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    # Filter out comments (keys starting with #)
                    if data:
                        return {k: v for k, v in data.items() if not k.startswith("#")}
                    return {}

        # Return empty glossary if not found
        return {}

    def load_style_guide(
        self,
        product: str,
        target_lang: str
    ) -> Dict[str, str]:
        """
        Load a product-specific style guide for a target language.

        Args:
            product: Product identifier (e.g., "abc_cloud")
            target_lang: Target language code (e.g., "en", "en-rUS", "ja")

        Returns:
            Style guide dict (e.g., {"tone": "formal", "voice": "active"})
        """
        data_dir = self.config_dir.parent / "data"
        style_dir = data_dir / "style_guides" / product

        # Normalize language code: "en-rUS" → "en"
        base_lang = target_lang.split("-")[0]

        candidates = [
            style_dir / f"{target_lang}.yaml",  # exact match (en-rUS.yaml)
            style_dir / f"{target_lang}.yml",
            style_dir / f"{base_lang}.yaml",    # base language (en.yaml)
            style_dir / f"{base_lang}.yml",
        ]

        for path in candidates:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data:
                        return {k: v for k, v in data.items() if not k.startswith("#")}
                    return {}

        # Return empty style guide if not found
        return {}

    def list_glossaries(self) -> List[Dict[str, Any]]:
        """List available glossaries with their products and languages"""
        data_dir = self.config_dir.parent / "data"
        glossary_base = data_dir / "glossaries"
        if not glossary_base.exists():
            return []

        glossaries = []
        for product_dir in glossary_base.iterdir():
            if product_dir.is_dir():
                product = product_dir.name
                for path in product_dir.glob("*.yaml"):
                    glossaries.append({
                        "product": product,
                        "language": path.stem,
                        "path": str(path)
                    })
                for path in product_dir.glob("*.yml"):
                    glossaries.append({
                        "product": product,
                        "language": path.stem,
                        "path": str(path)
                    })

        return glossaries

    def get_languages(self) -> List[Dict[str, Any]]:
        """Get list of target languages"""
        config = self.load("languages")
        return config.get("languages", [])

    def get_source_language(self) -> Dict[str, Any]:
        """Get source language configuration"""
        config = self.load("languages")
        return config.get("source", {"code": "ko", "name": "Korean"})

    def get_thresholds(self) -> Dict[str, Any]:
        """Get scoring and decision thresholds"""
        return self.load("thresholds")

    def get_model_config(self, role: str) -> Dict[str, Any]:
        """Get model configuration for a specific role"""
        config = self.load("models")
        models = config.get("models", {})
        if role not in models:
            raise ValueError(f"Unknown model role: {role}")
        return models[role]

    def clear_cache(self):
        """Clear the config cache"""
        self.load.cache_clear()


# Singleton instance
_default_loader: Optional[ConfigLoader] = None


def get_config_loader(config_dir: Optional[str] = None) -> ConfigLoader:
    """Get or create the default config loader singleton"""
    global _default_loader
    if _default_loader is None:
        _default_loader = ConfigLoader(config_dir)
    return _default_loader


def get_config(name: str) -> Dict[str, Any]:
    """Convenience function to load a config file"""
    loader = get_config_loader()
    return loader.load(name)


def get_thresholds() -> Dict[str, Any]:
    """Convenience function to get thresholds"""
    loader = get_config_loader()
    return loader.get_thresholds()


def get_risk_profile(country_code: str) -> Dict[str, Any]:
    """Convenience function to get a risk profile"""
    loader = get_config_loader()
    return loader.load_risk_profile(country_code)


def get_glossary(product: str, target_lang: str) -> Dict[str, str]:
    """
    Convenience function to get a glossary.

    Args:
        product: Product identifier (e.g., "abc_cloud")
        target_lang: Target language code (e.g., "en", "en-rUS", "ja")

    Returns:
        Glossary dict mapping source terms to target terms

    Example:
        glossary = get_glossary("abc_cloud", "en-rUS")
        # Returns: {"ABC 클라우드": "ABC Cloud", "동기화": "sync", ...}
    """
    loader = get_config_loader()
    return loader.load_glossary(product, target_lang)


def get_style_guide(product: str, target_lang: str) -> Dict[str, str]:
    """
    Convenience function to get a style guide.

    Args:
        product: Product identifier (e.g., "abc_cloud")
        target_lang: Target language code (e.g., "en", "en-rUS", "ja")

    Returns:
        Style guide dict (e.g., {"tone": "formal", "voice": "active"})

    Example:
        style = get_style_guide("abc_cloud", "en-rUS")
        # Returns: {"tone": "formal", "voice": "active", ...}
    """
    loader = get_config_loader()
    return loader.load_style_guide(product, target_lang)
