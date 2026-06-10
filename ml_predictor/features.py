# featutes.py

"""Подготовка данных каротажа: маппинг LAS, признаки, маски валидности."""

import numpy as np
import pandas as pd

from core.constants import BASE_FEATURES, LAS_NULL_VALUES, LAS_TO_FEATURE_MAP, NONCOLLECTOR_RULES
from core.utils import parse_bit_size


def map_las_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Маппинг колонок LAS на внутренние названия."""
    mapped_df = pd.DataFrame()

    for col in df.columns:
        col_upper = col.upper()
        if col_upper in LAS_TO_FEATURE_MAP:
            internal_name = LAS_TO_FEATURE_MAP[col_upper]
            mapped_df[internal_name] = df[col]
        else:
            mapped_df[col] = df[col]

    return mapped_df


def create_features(df: pd.DataFrame) -> pd.DataFrame:
    """Создание производных признаков для модели."""
    df = df.copy()

    # ЭТОТ ПРИЗНАК МОДЕЛЬ НЕ ИСПОЛЬЗУЕТ — МОЖНО УБРАТЬ
    # if 'BK' in df.columns and 'GR' in df.columns:
    #     df['BK_GR_ratio'] = df['BK'] / (df['GR'] + 1e-6)

    if 'NGR' in df.columns and 'GR' in df.columns:
        df['NGR_GR_ratio'] = df['NGR'] / (df['GR'] + 1e-6)

    if 'BK' in df.columns and 'DT' in df.columns:
        df['BK_DT_ratio'] = df['BK'] / (df['DT'] + 1e-6)

    # ЭТОТ ПРИЗНАК МОДЕЛЬ НЕ ИСПОЛЬЗУЕТ — МОЖНО УБРАТЬ
    # if 'BK' in df.columns:
    #     df['BK_log'] = np.log1p(df['BK'])

    # Глубину оставляем как есть!
    # if 'depth_carriage' in df.columns:
    #   depth_min = df['depth_carriage'].min()
    #   depth_max = df['depth_carriage'].max()
    #   df['depth_normalized'] = (df['depth_carriage'] - depth_min) / (depth_max - depth_min + 1e-6)

    return df


def check_required_features(df: pd.DataFrame, feature_columns) -> list:
    """Список отсутствующих базовых признаков ГИС."""
    return [f for f in BASE_FEATURES if f not in df.columns]


def get_valid_data_mask(df: pd.DataFrame) -> pd.Series:
    """
    Маска строк с полным комплексом ГИС (без NaN и кодов пропусков LAS).
    """
    mask = pd.Series([True] * len(df), index=df.index)

    for feature in BASE_FEATURES:
        if feature in df.columns:
            feature_valid = df[feature].notna()
            for null_val in LAS_NULL_VALUES:
                feature_valid = feature_valid & (df[feature] != null_val)
            mask = mask & feature_valid

    return mask


def _clean_gis_array(series: pd.Series) -> np.ndarray:
    values = pd.to_numeric(series, errors='coerce').to_numpy(dtype=float)
    for null_val in LAS_NULL_VALUES:
        values = np.where(values == null_val, np.nan, values)
    return values


def _resolve_bit_size_cm(
    mapped_df: pd.DataFrame,
    well_info: dict | None,
    bit_size_cm: float | None,
) -> float | None:
    """Диаметр долота в см: аргумент, BS из LAS (м → см) или медиана DS по интервалу."""
    if bit_size_cm is not None and bit_size_cm > 0:
        return float(bit_size_cm)
    bs_m = parse_bit_size(well_info or {})
    if bs_m is not None and bs_m > 0:
        return bs_m * 100.0
    if 'DS' in mapped_df.columns:
        ds = _clean_gis_array(mapped_df['DS'])
        valid = np.isfinite(ds)
        if valid.sum() > 0:
            return float(np.nanmedian(ds[valid]) * 100.0)
    return None


def _suppress_thin_nc_runs(mask: np.ndarray, min_run: int = 3) -> np.ndarray:
    """Снять NC с коротких прослоев (меньше min_run подряд идущих точек)."""
    out = mask.copy()
    n = len(mask)
    i = 0
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        if (j - i) < min_run:
            out[i:j] = False
        i = j
    return out


def noncollector_mask(
        mapped_df: pd.DataFrame,
        bit_size_cm: float | None = None,
        well_info: dict | None = None,
        valid_mask: pd.Series | None = None,
        rules: dict | None = None,
) -> np.ndarray:
    """
    Выделение неколлекторов по комплексу ГИС на основе непрерывных
    петрофизических коэффициентов (объем глинистости, акустическая плотность, контрастность БK).

    Логика выделения:
    1. Глинистый неколлектор: Оценивается реальный объем глины по Ларионову и
       падение относительного сопротивления до уровня глин.
    2. Плотный неколлектор: Оценивается падение интервального времени (DT)
       до значений матрицы породы при сохранении номинального диаметра ствола.
    """
    cfg = {**NONCOLLECTOR_RULES, **(rules or {})}
    n = len(mapped_df)
    out = np.zeros(n, dtype=bool)

    # Базовая проверка наличия необходимых каротажей
    required_cols = ['GR', 'DS', 'DT', 'BK']
    if not all(col in mapped_df.columns for col in required_cols):
        return out

    # Чистим массивы от кодов пропусков LAS
    gr = _clean_gis_array(mapped_df['GR'])
    ds_m = _clean_gis_array(mapped_df['DS'])
    dt = _clean_gis_array(mapped_df['DT'])
    bk = _clean_gis_array(mapped_df['BK'])

    # Создаем общую маску валидности данных
    valid = np.isfinite(gr) & np.isfinite(ds_m) & np.isfinite(dt) & np.isfinite(bk)
    if valid_mask is not None:
        valid = valid & np.asarray(valid_mask, dtype=bool)

    if valid.sum() < 2:
        return out

    # Получаем диаметр долота
    bit_cm = _resolve_bit_size_cm(mapped_df, well_info, bit_size_cm)
    if bit_cm is None:
        return out

    ds_cm = ds_m * 100.0

    # -------------------------------------------------------------------------
    # 1. РАСЧЕТ НЕПРЕРЫВНЫХ ПЕТРОФИЗИЧЕСКИХ КОЭФФИЦИЕНТОВ
    # -------------------------------------------------------------------------

    # Расчет индекса ГК (Iгр)
    gr_min = float(np.nanmin(gr[valid]))
    gr_max = float(np.nanmax(gr[valid]))
    denom = gr_max - gr_min
    igr = np.clip((gr - gr_min) / (denom + 1e-6), 0.0, 1.0)

    # Расчет истинного объема глинистости (Vsh) по нелинейной формуле Ларионова
    # (Выбираем вариант для более древних/сцементированных пород, например, Юра/Палеозой.
    # Если у вас молодой мел/неоген, можно заменить на: 0.33 * (2**(2*igr) - 1))
    v_shale = 1.7 * (3.5 ** igr - 1)
    v_shale = np.clip(v_shale, 0.0, 1.0)

    # Расчет относительного индекса пористости по акустике (I_dt)
    # Используем стандартные физические константы: матрица песчаника ~181 мкс/м, флюид ~640 мкс/м
    dt_matrix = 181.0
    dt_fluid = 640.0
    i_dt = (dt - dt_matrix) / (dt_fluid - dt_matrix + 1e-6)
    i_dt = np.clip(i_dt, 0.0, 1.0)

    # Автоматическое определение опорного сопротивления чистых глин в скважине
    # Ищем медиану БК в зонах, где индекс ГК > 0.75
    clay_zone_mask = valid & (igr > 0.75)
    if clay_zone_mask.sum() > 0:
        r_shale = float(np.nanmedian(bk[clay_zone_mask]))
    else:
        r_shale = float(cfg.get('bk_low', 4.0))  # Fallback, если чистых глин нет

    # Коэффициент относительного сопротивления (контрастность пласта к глинам)
    r_relative = bk / (r_shale + 1e-6)

    # -------------------------------------------------------------------------
    # 2. КРИТЕРИАЛЬНЫЙ СИНТЕЗ НЕКОЛЛЕКТОРОВ
    # -------------------------------------------------------------------------

    # Кавернозность (типично для неустойчивых глин)
    is_washout = valid & (ds_cm > bit_cm + cfg.get('washout_cm', 1.5))

    # Номинальный ствол (типично для плотных, крепких разностей)
    is_tight_hole = valid & (np.abs(ds_cm - bit_cm) < cfg.get('tight_hole_cm', 0.8))

    # Условие ГЛИНИСТОГО неколлектора:
    # Объем глины превышает критический порог (например, 35-40%)
    # И при этом либо ствол размыт (каверна), либо сопротивление упало до уровня глин
    clay_mask = valid & (v_shale > 0.38) & (is_washout | (r_relative < 1.3))

    # Условие ПЛОТНОГО неколлектора (плотняк):
    # Номинальный ствол (нет каверны) И очень низкое время пробега волны (пористость матрицы < 5-7%)
    # И высокое сопротивление (нет проводящих флюидов и глин)
    tight_mask = valid & is_tight_hole & (i_dt < 0.08) & (r_relative > 5.0)

    # Финальное объединение двух типов физических неколлекторов
    flagged = clay_mask | tight_mask

    # -------------------------------------------------------------------------
    # 3. ПОСТ-ФИЛЬТРАЦИЯ МИКРО-ПРОСЛОЕВ
    # -------------------------------------------------------------------------
    min_run = int(cfg.get('min_nc_run_points', 3))
    if min_run > 1 and flagged.any():
        flagged = _suppress_thin_nc_runs(flagged, min_run=min_run)

    return flagged