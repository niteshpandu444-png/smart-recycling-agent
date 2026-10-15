import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./smart_recycling.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

# SQLite WAL mode and foreign-key enforcement
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(target_engine=None):
    """
    Initializes database schema and ensures baseline virtual bins exist.
    """
    import backend.app.models  # Ensure all models are registered on Base.metadata
    eng = target_engine or engine
    Base.metadata.create_all(bind=eng)

    # Populate baseline virtual bins if not existing
    from backend.app.models import VirtualBin

    session = SessionLocal() if target_engine is None else sessionmaker(bind=target_engine)()
    try:
        existing_count = session.query(VirtualBin).count()
        if existing_count == 0:
            default_bins = [
                VirtualBin(
                    id="bin-plastic",
                    name="Plastic Recycling",
                    accepted_category="plastic",
                    capacity=100.0,
                    current_inventory=0.0,
                    inventory_unit="items",
                    status="normal",
                ),
                VirtualBin(
                    id="bin-paper",
                    name="Paper & Cardboard",
                    accepted_category="paper",
                    capacity=150.0,
                    current_inventory=0.0,
                    inventory_unit="items",
                    status="normal",
                ),
                VirtualBin(
                    id="bin-metal",
                    name="Metal & Cans",
                    accepted_category="metal",
                    capacity=80.0,
                    current_inventory=0.0,
                    inventory_unit="items",
                    status="normal",
                ),
                VirtualBin(
                    id="bin-glass",
                    name="Glass Bottles & Jars",
                    accepted_category="glass",
                    capacity=80.0,
                    current_inventory=0.0,
                    inventory_unit="items",
                    status="normal",
                ),
                VirtualBin(
                    id="bin-organic",
                    name="Compost & Organics",
                    accepted_category="organic",
                    capacity=120.0,
                    current_inventory=0.0,
                    inventory_unit="items",
                    status="normal",
                ),
                VirtualBin(
                    id="bin-holding",
                    name="Needs Verification",
                    accepted_category="holding",
                    capacity=50.0,
                    current_inventory=0.0,
                    inventory_unit="items",
                    status="normal",
                ),
            ]
            session.add_all(default_bins)
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
