# predictor.py
"""
Прогноз насыщения по точкам ГИС и сшивка интервалов для таблиц/Excel.
"""

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from core.constants import DEFAULT_PREDICTION_THRESHOLDS, SATURATION_NAMES
from ml_predictor.features import (
    check_required_features,
    create_features,
    get_valid_data_mask,
    map_las_columns,
    noncollector_mask,
)


def _patch_sklearn_imputer(imputer):
    """Совместимость SimpleImputer, сохранённого в sklearn 1.6, с sklearn 1.8+."""
    if imputer is None:
        return
    if (
        isinstance(imputer, SimpleImputer)
        and not hasattr(imputer, "_fill_dtype")
        and hasattr(imputer, "_fit_dtype")
    ):
        imputer._fill_dtype = imputer._fit_dtype


def _classifier_has_preprocessing(classifier) -> bool:
    if not hasattr(classifier, "named_steps"):
        return False
    steps = classifier.named_steps
    return "imputer" in steps or "scaler" in steps


def _prepare_model_input(model_bundle, X):
    """
    Подготовка матрицы признаков для predict_proba.

    ideal_pipeline из Colab уже содержит imputer и scaler — повторно их применять нельзя.
    """
    classifier = model_bundle.get("classifier", model_bundle)

    if _classifier_has_preprocessing(classifier):
        _patch_sklearn_imputer(classifier.named_steps.get("imputer"))
        return classifier, X

    X_out = X
    imputer = model_bundle.get("imputer")
    scaler = model_bundle.get("scaler")
    if imputer is not None:
        _patch_sklearn_imputer(imputer)
        try:
            X_out = imputer.transform(X_out)
        except Exception as e:
            raise RuntimeError(
                "Не удалось применить imputer из сохраненной модели. "
                "Переобучите/пересохраните модель в текущей версии sklearn. "
                f"Техническая ошибка: {e}"
            ) from e
    if scaler is not None:
        try:
            X_out = scaler.transform(X_out)
        except Exception as e:
            raise RuntimeError(
                "Не удалось применить scaler из сохраненной модели. "
                "Переобучите/пересохраните модель в текущей версии sklearn. "
                f"Техническая ошибка: {e}"
            ) from e

    if isinstance(classifier, Pipeline):
        classifier = classifier.named_steps.get("classifier", classifier)
    return classifier, X_out


def predict_with_thresholds(proba, thresholds):
    """
    Предсказание с настроенными порогами.
    Понижает порог для миноритарных классов (нефть, смесь).
    """
    if thresholds is None:
        thresholds = DEFAULT_PREDICTION_THRESHOLDS

    predictions = []
    for p in proba:
        if p[1] > thresholds['oil'] and p[1] > p[2]:
            predictions.append(2)
        elif p[2] > thresholds['mix'] and p[2] > p[1]:
            predictions.append(3)
        elif p[1] > thresholds['oil'] * 0.8 and p[2] > thresholds['mix'] * 0.8:
            predictions.append(2 if p[1] > p[2] else 3)
        else:
            predictions.append(np.argmax(p) + 1)
    return np.array(predictions)


def predict_saturation(df, model_bundle, feature_columns, thresholds=None, well_info=None):
    """
    Прогноз характера насыщения только для точек с полным комплексом ГИС.

    Returns:
        (DataFrame с прогнозами, None) или (None, сообщение об ошибке)
    """
    mapped_df = map_las_columns(df)

    if 'DEPT' in df.columns:
        mapped_df['depth_carriage'] = df['DEPT']

    missing = check_required_features(mapped_df, feature_columns)
    if missing:
        return None, f"Отсутствуют признаки: {', '.join(missing)}"

    valid_mask = get_valid_data_mask(mapped_df)
    n_valid = valid_mask.sum()
    n_total = len(df)

    if n_valid == 0:
        return None, "Нет точек с полным комплексом ГИС для прогноза"

    featured_df = create_features(mapped_df)
    missing_cols = [c for c in feature_columns if c not in featured_df.columns]
    if missing_cols:
        return None, f"Не удалось построить признаки: {', '.join(missing_cols)}"

    predictions = np.zeros(n_total, dtype=int)
    prob_water = np.zeros(n_total)
    prob_oil = np.zeros(n_total)
    prob_mix = np.zeros(n_total)

    if n_valid > 0:
        X_valid = featured_df.loc[valid_mask, feature_columns].values

        try:
            classifier, X_model = _prepare_model_input(model_bundle, X_valid)
        except RuntimeError as e:
            return None, str(e)

        valid_probabilities = classifier.predict_proba(X_model)
        valid_predictions = predict_with_thresholds(valid_probabilities, thresholds)

        predictions[valid_mask] = valid_predictions
        prob_water[valid_mask] = valid_probabilities[:, 0]
        prob_oil[valid_mask] = valid_probabilities[:, 1]
        prob_mix[valid_mask] = valid_probabilities[:, 2]

        vm = np.asarray(valid_mask, dtype=bool)
        nc_mask = noncollector_mask(
            mapped_df,
            well_info=well_info,
            valid_mask=valid_mask,
        )
        override = vm & nc_mask
        predictions[override] = 4
        prob_water[override] = 0.0
        prob_oil[override] = 0.0
        prob_mix[override] = 0.0

    results = pd.DataFrame({
        'Глубина': df['DEPT'].values if 'DEPT' in df.columns else np.arange(len(df)),
        'Прогноз': predictions,
        'Класс': [SATURATION_NAMES.get(int(p), '—') for p in predictions],
        'Вероятность_Вода': prob_water,
        'Вероятность_Нефть': prob_oil,
        'Вероятность_Смесь': prob_mix,
        'Данные_полные': valid_mask.values,
    })

    return results, None


def find_saturation_intervals(results: pd.DataFrame) -> list:
    """
    Сшивка подряд идущих точек с одним классом (Прогноз > 0) в интервалы.
    Интервалы с нулевой мощностью не включаются.
    """
    intervals = []
    results_filtered = results[results['Прогноз'] > 0]

    if len(results_filtered) == 0:
        return intervals

    current_class = results_filtered['Прогноз'].iloc[0]
    start_depth = results_filtered['Глубина'].iloc[0]

    for i in range(1, len(results_filtered)):
        if results_filtered['Прогноз'].iloc[i] != current_class:
            end_depth = results_filtered['Глубина'].iloc[i - 1]
            thickness = end_depth - start_depth
            if thickness > 0:
                intervals.append([
                    SATURATION_NAMES[current_class],
                    round(start_depth, 1),
                    round(end_depth, 1),
                    round(thickness, 1),
                ])
            current_class = results_filtered['Прогноз'].iloc[i]
            start_depth = results_filtered['Глубина'].iloc[i]

    end_depth = results_filtered['Глубина'].iloc[-1]
    thickness = end_depth - start_depth
    if thickness > 0:
        intervals.append([
            SATURATION_NAMES[current_class],
            round(start_depth, 1),
            round(end_depth, 1),
            round(thickness, 1),
        ])

    return intervals


def saturation_intervals_dataframe(results: pd.DataFrame) -> pd.DataFrame:
    """Таблица интервалов насыщения для UI и Excel."""
    cols = ['Тип насыщения', 'Кровля (м)', 'Подошва (м)', 'Мощность (м)']
    rows = find_saturation_intervals(results)
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)
