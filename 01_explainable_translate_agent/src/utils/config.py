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
        profile_dir = self.config_dir / "risk_profiles"
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
        profile_dir = self.config_dir / "risk_profiles"
        if not profile_dir.exists():
            return []

        profiles = []
        for path in profile_dir.glob("*.yaml"):
            profiles.append(path.stem)
        for path in profile_dir.glob("*.yml"):
            profiles.append(path.stem)

        return sorted(set(profiles))

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
