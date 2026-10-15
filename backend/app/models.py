import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Float,
    DateTime,
    Boolean,
    ForeignKey,
    JSON,
    Text,
    CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from backend.app.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Scan(Base):
    __tablename__ = "scans"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    image_url = Column(String(255), nullable=True)
    predicted_category = Column(String(50), nullable=False)
    confidence = Column(Float, nullable=False)
    model_identifier = Column(String(100), nullable=False, default="baseline-vision-v1")
    review_status = Column(String(30), nullable=False, default="pending")  # pending, needs_review, confirmed, rejected
    top_k_predictions = Column(JSON, nullable=True)
    margin = Column(Float, nullable=True)
    ocr_cues = Column(JSON, nullable=True)
    is_demo = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    # Relationships
    material_entry = relationship("MaterialEntry", back_populates="scan", uselist=False)
    events = relationship("MaterialEvent", back_populates="scan")


class MaterialEntry(Base):
    __tablename__ = "material_entries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    scan_id = Column(String(36), ForeignKey("scans.id"), unique=True, nullable=True)
    description = Column(String(255), nullable=True)
    category = Column(String(50), nullable=False)
    confirmed_category = Column(String(50), nullable=False)
    predicted_category = Column(String(50), nullable=True)
    quantity = Column(Float, nullable=False, default=1.0)
    unit = Column(String(20), nullable=False, default="items")
    destination = Column(String(50), nullable=False)
    processing_status = Column(String(30), nullable=False, default="confirmed")  # confirmed, holding, processed, reclassified, reversed
    confirmation_source = Column(String(50), nullable=False, default="model_accepted")  # model_accepted, user_visual, user_label_check, manual_override
    confidence_at_confirmation = Column(Float, nullable=True)
    verification_answers = Column(JSON, nullable=True)
    is_demo = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        CheckConstraint("quantity >= 0", name="chk_material_quantity_non_negative"),
        CheckConstraint("unit IN ('items', 'kg', 'g', 'l', 'units')", name="chk_material_allowed_units"),
    )

    # Relationships
    scan = relationship("Scan", back_populates="material_entry")
    events = relationship("MaterialEvent", back_populates="material_entry")


class VirtualBin(Base):
    __tablename__ = "virtual_bins"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    accepted_category = Column(String(50), nullable=False)
    capacity = Column(Float, nullable=False)
    current_inventory = Column(Float, nullable=False, default=0.0)
    inventory_unit = Column(String(20), nullable=False, default="items")
    status = Column(String(30), nullable=False, default="normal")  # normal, warning, full, maintenance
    is_demo = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        CheckConstraint("capacity > 0", name="chk_bin_capacity_positive"),
        CheckConstraint("current_inventory >= 0", name="chk_bin_inventory_non_negative"),
    )


class MaterialEvent(Base):
    __tablename__ = "material_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    event_type = Column(String(50), nullable=False)  # confirmed, routed, reclassified, emptied, transferred, processed, reversal
    material_id = Column(String(36), ForeignKey("material_entries.id"), nullable=True)
    scan_id = Column(String(36), ForeignKey("scans.id"), nullable=True)
    source_bin_id = Column(String(50), ForeignKey("virtual_bins.id"), nullable=True)
    destination_bin_id = Column(String(50), ForeignKey("virtual_bins.id"), nullable=True)
    quantity = Column(Float, nullable=False)
    unit = Column(String(20), nullable=False, default="items")
    affected_category = Column(String(50), nullable=False)
    payload = Column(JSON, nullable=True)
    idempotency_key = Column(String(128), unique=True, nullable=True)
    is_demo = Column(Boolean, nullable=False, default=False)
    timestamp = Column(DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        CheckConstraint("quantity >= 0", name="chk_event_quantity_non_negative"),
    )

    # Relationships
    material_entry = relationship("MaterialEntry", back_populates="events")
    scan = relationship("Scan", back_populates="events")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    title = Column(String(150), nullable=False)
    recommendation_text = Column(Text, nullable=False)
    generation_method = Column(String(50), nullable=False)  # llm | deterministic_fallback
    supporting_data = Column(JSON, nullable=False)
    status = Column(String(30), nullable=False, default="new")  # new, acknowledged, dismissed, resolved
    data_hash = Column(String(64), nullable=True)
    is_demo = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class SnapshotRecord(Base):
    __tablename__ = "snapshot_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    timestamp = Column(DateTime, nullable=False, default=utc_now)
    total_items = Column(Float, nullable=False)
    bin_states = Column(JSON, nullable=False)
    is_demo = Column(Boolean, nullable=False, default=False)


class SimulationSetting(Base):
    __tablename__ = "simulation_settings"

    key = Column(String(50), primary_key=True)
    value = Column(JSON, nullable=False)
    description = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
