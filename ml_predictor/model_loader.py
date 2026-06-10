# model_loader.py

"""Загрузка обученной модели и списка признаков."""

import os
import joblib
import streamlit as st


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(_PROJECT_ROOT, 'models')
MODEL_PATH = os.path.join(MODEL_DIR, 'saturation_model.joblib')

def _ensure_ml_deps():
    """Модель сериализована с CatBoost — без пакета joblib.load падает с ModuleNotFoundError."""
    try:
        import catboost  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "Для загрузки модели нужен пакет catboost. "
            "Установите зависимости проекта: pip install -r requirements.txt"
        ) from exc


def _load_model():
    """Загрузка модели из единого файла бандла (без использования внешнего файла признаков)."""
    if not os.path.exists(MODEL_PATH):
        return None, None, None

    _ensure_ml_deps()
    model_bundle = joblib.load(MODEL_PATH)

    if isinstance(model_bundle, dict):
        feature_columns = model_bundle.get('feature_columns')
        thresholds = model_bundle.get('thresholds')
        return model_bundle, feature_columns, thresholds

    return None, None, None


@st.cache_resource(show_spinner="Загрузка ML-модели...")
def load_model_cached():
    return _load_model()
