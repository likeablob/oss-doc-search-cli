"""
Pydantic models for library definitions and manifest.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class DocSourceType(StrEnum):
    repo_path = "repo_path"
    separate_repo = "separate_repo"


class DocSource(BaseModel):
    type: DocSourceType = Field(..., description="Doc source type")
    repo: str = Field(..., description="Repository to clone (required for all types)")
    path: str = Field(..., description="Docs folder path")
    extensions: list[str] = Field(..., description="File extensions")
    ref: str | None = Field(None, description="Git branch or tag")

    @field_validator("extensions")
    @classmethod
    def validate_extensions(cls, v: list[str]) -> list[str]:
        for ext in v:
            if not ext.startswith(".") or len(ext) < 2:
                raise ValueError(
                    f"Extension must start with '.' and have at least 2 chars: {ext}"
                )
        return v


class Filters(BaseModel):
    include: list[str] = Field(
        default_factory=list, description="Glob patterns to include"
    )
    exclude: list[str] = Field(
        default_factory=list, description="Glob patterns to exclude"
    )


class LibraryDefinition(BaseModel):
    """Library definition from registry YAML."""

    id: str = Field(
        ...,
        description="Unique ID",
        pattern=r"^/[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+(/[a-zA-Z0-9_-]+)?$",
    )
    name: str = Field(..., description="Human-readable name")
    repo: str = Field(
        ...,
        description="Upstream repository",
        pattern=r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+$",
    )
    description: str | None = Field(None, description="Short description")
    doc_source: DocSource = Field(..., description="Doc source")
    filters: Filters = Field(default_factory=Filters, description="File filters")
    license: str = Field(..., description="License identifier")


class LibraryManifestEntry(BaseModel):
    """Library entry in manifest.json."""

    id: str
    name: str
    repo: str
    doc_repo: str | None = None
    license: str
    description: str | None = None
    indexed: bool = False
    chunks: int | None = None
    index_size_mb: float | None = None
    index_url: str | None = None
    index_filename: str | None = None
    index_hash: str | None = None
    commit_sha: str | None = None
    updated_at: str | None = None
    inherited: bool | None = None


class Manifest(BaseModel):
    """Manifest.json structure."""

    manifest_version: str
    release_tag: str
    release_base_url: str
    generated_at: str
    total_libraries: int
    indexed_count: int | None = None
    missing_count: int | None = None
    inherited_count: int | None = None
    new_count: int | None = None
    libraries: list[LibraryManifestEntry] = Field(default_factory=list)

    @field_validator("generated_at", mode="before")
    @classmethod
    def parse_datetime(cls, v: str | datetime) -> str:
        if isinstance(v, datetime):
            return v.isoformat()
        return v
