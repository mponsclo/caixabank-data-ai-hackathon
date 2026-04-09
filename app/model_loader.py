"""Load serialized ML models at startup."""

import os
import joblib

MODELS_DIR = os.environ.get("MODELS_DIR", "outputs/models")


def _safe_load(path: str, label: str) -> object | None:
    """Load a pkl file, returning None on any error."""
    if not os.path.exists(path):
        return None
    try:
        return joblib.load(path)
    except Exception as e:
        print(f"Warning: failed to load {label} from {path}: {e}")
        return None


def load_models() -> dict:
    """Load fraud and forecast models from disk.

    Returns a dict with available model artifacts. The app starts
    gracefully even if some or all models fail to load.
    """
    models = {}

    fraud = _safe_load(os.path.join(MODELS_DIR, "fraud_model.pkl"), "fraud_model")
    if fraud:
        models["fraud_model"] = fraud

    for h in [1, 2, 3]:
        m = _safe_load(os.path.join(MODELS_DIR, f"forecast_h{h}.pkl"), f"forecast_h{h}")
        if m:
            models[f"forecast_h{h}"] = m

    te = _safe_load(os.path.join(MODELS_DIR, "target_encodings.pkl"), "target_encodings")
    if te:
        models["target_encodings"] = te

    meta = _safe_load(os.path.join(MODELS_DIR, "feature_metadata.pkl"), "feature_metadata")
    if meta:
        models["feature_metadata"] = meta

    print(f"Loaded {len(models)} model artifacts from {MODELS_DIR}")
    return models
