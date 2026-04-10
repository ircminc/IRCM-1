"""SQLAlchemy ORM table definitions for parsed billing data."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime,
    Boolean, Text, ForeignKey, Index
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class ParsedFile(Base):
    __tablename__ = "files"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    filename   = Column(String(255), nullable=False)
    tx_type    = Column(String(10), nullable=False)
    upload_ts  = Column(DateTime, default=datetime.utcnow)
    parsed_ts  = Column(DateTime)
    status     = Column(String(20), default="pending")  # pending, parsed, error
    error_msg  = Column(Text)
    record_count = Column(Integer, default=0)
    file_size_bytes = Column(Integer, default=0)

    claims     = relationship("Claim837", back_populates="file", cascade="all, delete-orphan")
    payments   = relationship("ClaimPayment835", back_populates="file", cascade="all, delete-orphan")


class Claim837(Base):
    __tablename__ = "claims_837"
    __table_args__ = (
        Index("ix_claims_837_file_id",    "file_id"),
        Index("ix_claims_837_payer_id",   "payer_id"),
        Index("ix_claims_837_dos_from",   "dos_from"),
        Index("ix_claims_837_provider",   "billing_provider_npi"),
    )
    id                   = Column(Integer, primary_key=True, autoincrement=True)
    file_id              = Column(Integer, ForeignKey("files.id"), nullable=False)
    claim_id             = Column(String(50))
    total_billed         = Column(Float)
    place_of_service     = Column(String(10))
    claim_frequency      = Column(String(5))
    claim_filing_indicator = Column(String(5))
    group_number         = Column(String(50))
    payer_id             = Column(String(50))
    payer_name           = Column(String(100))
    billing_provider_npi = Column(String(15))
    billing_provider_name = Column(String(100))
    subscriber_id        = Column(String(50))
    subscriber_last      = Column(String(50))
    subscriber_first     = Column(String(50))
    patient_last         = Column(String(50))
    patient_first        = Column(String(50))
    patient_dob          = Column(Date)
    dos_from             = Column(Date)
    dos_to               = Column(Date)
    principal_dx         = Column(String(10))
    claim_note           = Column(Text)
    payer_claim_number   = Column(String(50))

    file               = relationship("ParsedFile", back_populates="claims")
    service_lines      = relationship("ServiceLine837", back_populates="claim", cascade="all, delete-orphan")


class ServiceLine837(Base):
    __tablename__ = "service_lines_837"
    __table_args__ = (
        Index("ix_sl_claim_id", "claim_id"),
        Index("ix_sl_cpt",      "cpt_hcpcs"),
    )
    id                = Column(Integer, primary_key=True, autoincrement=True)
    claim_id          = Column(Integer, ForeignKey("claims_837.id"), nullable=False)
    line_number       = Column(String(5))
    cpt_hcpcs         = Column(String(10))
    modifier_1        = Column(String(5))
    modifier_2        = Column(String(5))
    billed_amount     = Column(Float)
    units             = Column(String(10))
    place_of_service  = Column(String(10))
    diagnosis_pointers = Column(String(20))
    ndc               = Column(String(20))
    rendering_provider_npi = Column(String(15))

    claim = relationship("Claim837", back_populates="service_lines")


class ClaimPayment835(Base):
    __tablename__ = "claim_payments_835"
    __table_args__ = (
        Index("ix_cp835_file_id",    "file_id"),
        Index("ix_cp835_payer_id",   "payer_id"),
        Index("ix_cp835_status",     "status_code"),
        Index("ix_cp835_payment_date", "payment_date"),
    )
    id                   = Column(Integer, primary_key=True, autoincrement=True)
    file_id              = Column(Integer, ForeignKey("files.id"), nullable=False)
    clp_id               = Column(String(50))
    status_code          = Column(String(5))
    billed               = Column(Float)
    paid                 = Column(Float)
    patient_responsibility = Column(Float)
    claim_filing_indicator = Column(String(5))
    payer_claim_number   = Column(String(50))
    payer_id             = Column(String(50))
    payer_name           = Column(String(100))
    patient_name         = Column(String(100))
    payment_date         = Column(Date)

    file        = relationship("ParsedFile", back_populates="payments")
    adjustments = relationship("Adjustment835", back_populates="payment", cascade="all, delete-orphan")


class Adjustment835(Base):
    __tablename__ = "adjustments_835"
    __table_args__ = (
        Index("ix_adj835_payment_id",  "payment_id"),
        Index("ix_adj835_group_code",  "group_code"),
        Index("ix_adj835_reason_code", "reason_code"),
        Index("ix_adj835_file_id",     "file_id"),
    )
    id           = Column(Integer, primary_key=True, autoincrement=True)
    payment_id   = Column(Integer, ForeignKey("claim_payments_835.id"), nullable=False)
    file_id      = Column(Integer, ForeignKey("files.id"), nullable=False)
    group_code   = Column(String(5))
    reason_code  = Column(String(10))
    amount       = Column(Float)
    level        = Column(String(10))  # "claim" or "service"
    cpt_hcpcs    = Column(String(10))  # only for service-level

    payment = relationship("ClaimPayment835", back_populates="adjustments")
