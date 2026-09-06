from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SourceCategory(StrEnum):
    GOVERNMENT_OPEN_DATA = "government_open_data"
    GOVERNMENT_DIRECTORY = "government_directory"
    PROFESSIONAL_REGISTRY = "professional_registry"
    ACCREDITATION_DIRECTORY = "accreditation_directory"
    INSURER_NETWORK = "insurer_network"
    HOSPITAL_NETWORK = "hospital_network"
    HOSPITAL_WEBSITE = "hospital_website"
    HEALTHCARE_DIRECTORY = "healthcare_directory"
    OTHER_PUBLIC_SOURCE = "other_public_source"


class SourceStatus(StrEnum):
    DISCOVERED = "discovered"
    ACCESS_REVIEW_PENDING = "access_review_pending"
    PERMISSION_PENDING = "permission_pending"
    VERIFICATION_ONLY = "verification_only"
    FIXTURE_REQUIRED = "fixture_required"
    PARSER_TESTING = "parser_testing"
    REVIEW_BATCH_REQUIRED = "review_batch_required"
    APPROVED = "approved"
    SUSPENDED = "suspended"
    REJECTED = "rejected"


class SourceUsage(StrEnum):
    DISCOVERY = "discovery"
    VERIFICATION = "verification"
    INGESTION = "ingestion"


class AccessMode(StrEnum):
    AUTOMATED_PUBLIC = "automated_public"
    OFFICIAL_FILE_IMPORT = "official_file_import"
    VERIFICATION_ONLY = "verification_only"
    PERMISSION_REQUIRED = "permission_required"


class VerificationStatus(StrEnum):
    NEW = "new"
    COLLECTED = "collected"
    NORMALIZED = "normalized"
    VALIDATED = "validated"
    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"
    CONFLICT = "conflict"
    STALE = "stale"
    REJECTED = "rejected"
    INACTIVE = "inactive"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Evidence(BaseModel):
    field_name: str
    value: Any
    source: str
    source_url: str
    observed_at: datetime = Field(default_factory=utc_now)
    confidence: float = Field(ge=0, le=1)


class Hospital(BaseModel):
    hospital_id: str
    name: str
    name_en: str | None = None
    name_hi: str | None = None
    hospital_type: str | None = None
    type: str | None = None
    address: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    locality: str | None = None
    landmark: str | None = None
    city: str
    state: str | None = None
    pincode: str | None = None
    country: str = "India"
    phone: str | None = None
    phone_1: str | None = None
    phone_2: str | None = None
    emergency_phone: str | None = None
    email: str | None = None
    website: str | None = None
    emergency_available: bool | None = None
    departments: list[str] = Field(default_factory=list)
    latitude: float | None = None
    longitude: float | None = None
    source: str
    source_url: str
    source_record_id: str | None = None
    first_seen_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime = Field(default_factory=utc_now)
    last_verified_at: datetime | None = None
    verification_status: VerificationStatus = VerificationStatus.NEW
    verification_score: float = 0
    field_conflicts: list[str] = Field(default_factory=list)
    raw_record_reference: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class Doctor(BaseModel):
    doctor_id: str
    registration_number: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    full_name: str
    gender: str | None = None
    department_name_en: str | None = None
    department_name_hi: str | None = None
    specialization: str | None = None
    subspecialization: str | None = None
    medical_council: str | None = None
    qualification: str | None = None
    education_degrees: str | None = None
    experience_years: int | None = None
    about_en: str | None = None
    about_hi: str | None = None
    languages_spoken: str | None = None
    phone_1: str | None = None
    phone_2: str | None = None
    country_code_1: str | None = None
    country_code_2: str | None = None
    email: str | None = None
    website: str | None = None
    profile_url: str | None = None
    consultation_fee: float | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    locality: str | None = None
    landmark: str | None = None
    city: str
    state: str | None = None
    pincode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    organization_name: str | None = None
    source: str
    source_url: str
    source_record_id: str | None = None
    first_seen_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime = Field(default_factory=utc_now)
    last_verified_at: datetime | None = None
    verification_status: VerificationStatus = VerificationStatus.NEW
    verification_score: float = 0
    field_conflicts: list[str] = Field(default_factory=list)
    raw_record_reference: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class DoctorHospitalLink(BaseModel):
    doctor_hospital_link_id: str
    doctor_id: str
    hospital_id: str | None = None
    hospital_name: str
    hospital_city: str
    doctor_hospital_role: str | None = None
    consultation_mode: str | None = None
    availability: str | None = None
    days_of_week: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    hospital_consultation_fee: float | None = None
    relationship_source_url: str
    relationship_last_verified_at: datetime | None = None
