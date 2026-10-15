"""
Demo Data Seeding Script.
Populates realistic presentation data strictly through the REAL confirmation and Digital Twin workflows.
All records are explicitly tagged with `is_demo=True`.
SAFETY: Must be explicitly invoked with the `--seed-demo` argument to prevent accidental execution.
"""
import sys
import argparse
import logging
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal, init_db
from backend.app.models import Scan, VirtualBin, MaterialEntry, MaterialEvent
from backend.app.services.material_service import confirm_material, reclassify_material
from backend.app.services.recommendation_service import generate_recommendation
from backend.app.adapters.schemas import MaterialConfirmRequest, ReclassifyRequest

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("smart_recycling.seed_demo")


def run_seed(db: Session) -> None:
    logger.info("Initializing baseline schema and virtual bins...")
    init_db()

    # Define realistic demo items
    demo_scans = [
        {
            "id": "demo-scan-1",
            "image_url": "uploads/demo_pete_bottle.jpg",
            "predicted_category": "plastic",
            "confidence": 0.94,
            "top_k": [{"category": "plastic", "score": 0.94}, {"category": "glass", "score": 0.04}],
            "confirm_category": "plastic",
            "quantity": 12.0,
            "source": "model_accepted",
            "desc": "Clear PET water bottle (0.5L)",
        },
        {
            "id": "demo-scan-2",
            "image_url": "uploads/demo_soda_can.jpg",
            "predicted_category": "metal",
            "confidence": 0.98,
            "top_k": [{"category": "metal", "score": 0.98}, {"category": "plastic", "score": 0.01}],
            "confirm_category": "metal",
            "quantity": 8.0,
            "source": "model_accepted",
            "desc": "Aluminum beverage can",
        },
        {
            "id": "demo-scan-3",
            "image_url": "uploads/demo_shipping_box.jpg",
            "predicted_category": "paper",
            "confidence": 0.91,
            "top_k": [{"category": "paper", "score": 0.91}, {"category": "plastic", "score": 0.05}],
            "confirm_category": "paper",
            "quantity": 18.0,
            "source": "model_accepted",
            "desc": "Corrugated cardboard packaging box",
        },
        {
            "id": "demo-scan-4",
            "image_url": "uploads/demo_lookalike_cup.jpg",
            "predicted_category": "paper",
            "confidence": 0.62,
            "top_k": [{"category": "paper", "score": 0.54}, {"category": "plastic", "score": 0.46}],
            "margin": 0.08,
            "confirm_category": "paper",
            "quantity": 4.0,
            "source": "model_accepted",
            "desc": "Coffee cup with unknown internal lining",
        },
        {
            "id": "demo-scan-5",
            "image_url": "uploads/demo_takeaway_container.jpg",
            "predicted_category": "plastic",
            "confidence": 0.65,
            "top_k": [{"category": "compostable", "score": 0.51}, {"category": "plastic", "score": 0.49}],
            "margin": 0.02,
            "confirm_category": "compostable",
            "quantity": 5.0,
            "source": "user_visual",
            "desc": "Takeaway food container marked PLA #7",
            "answers": {"resin_code": "7", "commercial_compost_label": True},
        },
    ]

    logger.info("Executing demo confirmation flow...")
    confirmed_entries = []

    for item in demo_scans:
        # Check if already seeded
        existing_scan = db.query(Scan).filter(Scan.id == item["id"]).first()
        if not existing_scan:
            scan = Scan(
                id=item["id"],
                image_url=item.get("image_url"),
                predicted_category=item["predicted_category"],
                confidence=item["confidence"],
                model_identifier="demo-seed-v1",
                review_status="pending",
                top_k_predictions=item.get("top_k"),
                margin=item.get("margin"),
                is_demo=True,
            )
            db.add(scan)
            db.commit()
        else:
            scan = existing_scan

        # Check if already confirmed
        existing_entry = db.query(MaterialEntry).filter(MaterialEntry.scan_id == scan.id).first()
        if not existing_entry:
            req = MaterialConfirmRequest(
                scan_id=scan.id,
                confirmed_category=item["confirm_category"],
                quantity=item["quantity"],
                unit="items",
                confirmation_source=item["source"],
                description=item["desc"],
                verification_answers=item.get("answers"),
                idempotency_key=f"demo-seed-key-{scan.id}",
            )
            entry = confirm_material(db, req)
            entry.is_demo = True
            db.commit()
            confirmed_entries.append(entry)
            logger.info(f"Confirmed: {entry.description} -> {entry.destination} (Qty: {entry.quantity})")

    # Perform a demonstration reclassification
    # Move item demo-scan-4 from holding bin to plastic after secondary sorting
    holding_entry = (
        db.query(MaterialEntry)
        .filter(MaterialEntry.scan_id == "demo-scan-4", MaterialEntry.processing_status == "holding")
        .first()
    )
    if holding_entry:
        logger.info(f"Reclassifying holding item {holding_entry.id} following manual inspection...")
        reclass_req = ReclassifyRequest(
            target_category="plastic",
            target_bin_id="bin-plastic",
            reason="Confirmed plastic PE interior film coating upon tactile test",
            verification_answers={"lining_test": "plastic_film", "tears_fibers": False},
            idempotency_key="demo-reclass-item-4",
        )
        reclassify_material(db, material_id=holding_entry.id, request=reclass_req)

    # Generate initial contextual recommendation
    logger.info("Generating grounded demo recommendation...")
    rec = generate_recommendation(db, force_refresh=True, client_id="demo_seeder")
    rec.is_demo = True
    db.commit()
    logger.info(f"Generated demo recommendation: '{rec.title}' ({rec.generation_method})")
    logger.info("Demo seeding completed successfully! All records tagged with is_demo=True.")


def main():
    parser = argparse.ArgumentParser(description="Seed realistic demo data into Smart Recycling database.")
    parser.add_argument(
        "--seed-demo",
        action="store_true",
        help="Explicit confirmation to run the demo seeder on the configured database.",
    )
    args = parser.parse_args()

    if not args.seed_demo:
        print("SAFETY GUARD: To seed demo data, you must pass the --seed-demo flag.")
        print("Example: python backend/scripts/seed_demo.py --seed-demo")
        sys.exit(1)

    db = SessionLocal()
    try:
        run_seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
