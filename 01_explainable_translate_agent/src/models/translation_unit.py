"""
Translation Unit - Single FAQ item for translation
"""

from pydantic import BaseModel, Field
from typing import Dict


class TranslationUnit(BaseModel):
    """번역 단위 - 단일 FAQ 항목"""

    # Required fields
    key: str = Field(..., description="FAQ key (e.g., IDS_FAQ_SC_ABOUT)")
    source_text: str = Field(..., description="Source text (Korean)")
    source_lang: str = Field(default="ko", description="Source language code")
    target_lang: str = Field(..., description="Target language code (e.g., en-rUS)")

    # Context
    glossary: Dict[str, str] = Field(
        default_factory=dict,
        description="Term glossary mapping (source term -> target term)"
    )
    risk_profile: str = Field(
        default="DEFAULT",
        description="Country-specific risk profile (e.g., US, EU, CN)"
    )
    style_guide: Dict[str, str] = Field(
        default_factory=dict,
        description="Tone and formality guidelines"
    )

    # Metadata
    faq_version: str = Field(default="v1.0", description="FAQ content version")
    glossary_version: str = Field(default="v1.0", description="Glossary version")
    product: str = Field(default="abc_cloud", description="Product identifier")

    class Config:
        json_schema_extra = {
            "example": {
                "key": "IDS_FAQ_SC_ABOUT",
                "source_text": "ABC 클라우드는 사용자의 ABC 계정과 연동된 정보에 대한 동기화와 백업/복원을 지원하는 서비스입니다.",
                "source_lang": "ko",
                "target_lang": "en-rUS",
                "glossary": {
                    "ABC 클라우드": "ABC Cloud",
                    "ABC 계정": "ABC account",
                    "동기화": "sync"
                },
                "risk_profile": "US",
                "product": "abc_cloud"
            }
        }
