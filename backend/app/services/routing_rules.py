"""
Routing Rules and Confusable-Pair Registry.
Application and simulation routing definitions.
NOTE: These represent application/simulation routing policies, NOT municipal or industrial facility certification.
"""
from typing import Optional, List, Dict, Any, Tuple

# Standard category-to-virtual-bin mappings
DEFAULT_CATEGORY_BIN_MAPPING: Dict[str, str] = {
    "plastic": "bin-plastic",
    "paper": "bin-paper",
    "metal": "bin-metal",
    "glass": "bin-glass",
    "organic": "bin-organic",
    "biodegradable": "bin-organic",
    "compostable": "bin-organic",
    "holding": "bin-holding",
    # These categories are not accepted by the standard material bins. Keep
    # them in verification until a supported authorized destination is configured.
    "hazardous": "bin-holding",
    "reusable": "bin-holding",
}

# The conservative holding bin for ambiguous items
HOLDING_BIN_ID = "bin-holding"

# Thresholds for ambiguity detection
CONFIDENCE_THRESHOLD = 0.70
MARGIN_THRESHOLD = 0.15

# Registered pairs of visually or materially confusable classes
# e.g., PLA compostable cups look like PET plastic cups; paper cups often have plastic linings.
CONFUSABLE_PAIRS: List[Tuple[str, str]] = [
    ("paper", "plastic"),
    ("plastic", "paper"),
    ("compostable", "plastic"),
    ("plastic", "compostable"),
    ("organic", "plastic"),
    ("plastic", "organic"),
]

# Registered look-alike item descriptions/keywords known to cause high contamination risk
CONFUSABLE_ITEM_KEYWORDS: List[str] = [
    "cup",
    "lid",
    "cutlery",
    "fork",
    "knife",
    "spoon",
    "film",
    "bag",
    "pouch",
    "lining",
    "carton",
    "straw",
    "container",
    "tea bag",
]


def is_confusable_pair(cat1: str, cat2: str) -> bool:
    """Checks if two categories form a registered confusable group."""
    c1, c2 = cat1.lower().strip(), cat2.lower().strip()
    return (c1, c2) in CONFUSABLE_PAIRS or (c2, c1) in CONFUSABLE_PAIRS


def evaluate_uncertainty(
    confidence: float,
    predicted_category: str,
    top_k: Optional[List[Dict[str, Any]]] = None,
    margin: Optional[float] = None,
    description: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Evaluates whether an item is ambiguous and requires conservative routing to the holding bin.
    Returns (is_ambiguous, reason).
    """
    # 1. Check confidence threshold
    if confidence < CONFIDENCE_THRESHOLD:
        return True, f"Confidence {confidence:.2f} is below threshold {CONFIDENCE_THRESHOLD:.2f}"

    # 2. Check top-k margin and confusable classes
    if top_k and len(top_k) >= 2:
        top1 = top_k[0].get("category", "").lower()
        top2 = top_k[1].get("category", "").lower()
        score1 = float(top_k[0].get("score", 0.0))
        score2 = float(top_k[1].get("score", 0.0))
        score_margin = margin if margin is not None else (score1 - score2)

        if is_confusable_pair(top1, top2):
            if score_margin < MARGIN_THRESHOLD:
                return True, (
                    f"Top classes '{top1}' and '{top2}' form a confusable pair with narrow margin {score_margin:.2f}"
                )

    # 3. Check description keyword cues if provided
    if description:
        desc_lower = description.lower()
        for kw in CONFUSABLE_ITEM_KEYWORDS:
            if kw in desc_lower and predicted_category in ("paper", "plastic", "compostable", "organic"):
                # If confidence isn't exceptionally high, flag for caution
                if confidence < 0.85:
                    return True, f"Item description '{kw}' is a known look-alike risk at confidence {confidence:.2f}"

    return False, "Confidence and classification meet standard routing criteria"


def resolve_destination(
    category: str,
    is_ambiguous: bool = False,
    requested_destination: Optional[str] = None,
) -> str:
    """
    Resolves the target virtual bin.
    If explicitly marked ambiguous or if routing defaults to holding, directs to HOLDING_BIN_ID.
    """
    if requested_destination:
        return requested_destination

    if is_ambiguous:
        return HOLDING_BIN_ID

    cat = category.lower().strip()
    return DEFAULT_CATEGORY_BIN_MAPPING.get(cat, HOLDING_BIN_ID)
