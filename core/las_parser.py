# las_parser.py
import re
from typing import Dict, Tuple
import lasio
import numpy as np
import pandas as pd

from core.constants import LAS_NULL_VALUES, UNIT_TRANSLATIONS
_ENCODINGS = ('cp866', 'cp1251', 'utf-8', 'latin-1')
# Символы, характерные для cp1251-ошибочного чтения cp866-текста
_MOJIBAKE_MARKERS = frozenset('Ђђ‹ЌЉЏЋЊЃѓ')


def _score_decoded_text(text: str) -> int:
    sample = text[:12000]
    cyrillic = sum(1 for ch in sample if '\u0400' <= ch <= '\u04FF')
    replacement = sample.count('\ufffd')
    mojibake = sum(1 for ch in sample if ch in _MOJIBAKE_MARKERS)
    return cyrillic * 5 - replacement * 50 - mojibake * 3


def _decode_las_bytes(raw_bytes: bytes) -> str:
    """Декодирование LAS: cp866/cp1251 для русских файлов, fallback на utf-8."""
    best_text = None
    best_score = float('-inf')

    for encoding in _ENCODINGS:
        try:
            text = raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
        score = _score_decoded_text(text)
        if score > best_score:
            best_score = score
            best_text = text

    if best_text is not None:
        return best_text
    return raw_bytes.decode('utf-8', errors='replace')


def _sanitize_las_text(text: str) -> str:
    """Удаляет типичный маркер конца файла (.LAS), мешающий lasio."""
    lines = text.splitlines()
    while lines and lines[-1].strip() in ('.LAS', ''):
        lines.pop()
    if not lines:
        return text
    return '\n'.join(lines) + '\n'


def _format_header_value(value) -> str:
    if value is None:
        return ''
    if isinstance(value, float) and np.isnan(value):
        return ''
    if isinstance(value, (np.integer, int)):
        return str(int(value))
    if isinstance(value, (np.floating, float)):
        return str(float(value))
    return str(value).strip()


def _extract_well_info(las: lasio.LASFile) -> Dict[str, str]:
    """Объединяет секции ~Well и ~Parameter в единый словарь метаданных."""
    info: Dict[str, str] = {}
    for section in (las.well, las.params):
        for item in section:
            key = item.mnemonic.strip().upper()
            if not key:
                continue
            info[key] = _format_header_value(item.value)
    return info


def _extract_units(las: lasio.LASFile) -> Dict[str, str]:
    units: Dict[str, str] = {}
    for curve in las.curves:
        mnem = curve.mnemonic.strip().upper()
        unit = (curve.unit or '').strip()
        units[mnem] = UNIT_TRANSLATIONS.get(unit.upper(), unit)
    return units


def _apply_null_values(df: pd.DataFrame, las: lasio.LASFile) -> pd.DataFrame:
    null_val = None
    if 'NULL' in las.well:
        null_val = las.well.NULL.value
    nulls = set(LAS_NULL_VALUES)
    if null_val is not None:
        nulls.add(null_val)

    result = df.copy()
    for col in result.columns:
        result[col] = pd.to_numeric(result[col], errors='coerce')
    return result.replace(list(nulls), np.nan)


def _las_to_dataframe(las: lasio.LASFile) -> pd.DataFrame:
    df = las.df().reset_index()
    df.columns = [str(col).strip().upper() for col in df.columns]

    if 'DEPT' not in df.columns and len(las.curves) > 0:
        depth_mnem = las.curves[0].mnemonic.strip().upper()
        if depth_mnem in df.columns:
            df = df.rename(columns={depth_mnem: 'DEPT'})

    return _apply_null_values(df, las)


def _load_data_fallback(las: lasio.LASFile, text: str) -> None:
    """Загрузка ~A секции вручную, если lasio не может прочитать данные."""
    n_curves = len(las.curves)
    if n_curves == 0:
        raise ValueError('Не найдены кривые в файле')

    in_data = False
    data_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('~A'):
            in_data = True
            continue
        if in_data and stripped and not stripped.startswith('#'):
            data_lines.append(stripped)

    if not data_lines:
        raise ValueError('Не найдены числовые данные')

    data_str = ' '.join(data_lines)
    numbers = np.array(
        [float(x) for x in re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', data_str)],
        dtype=float,
    )
    n_rows = len(numbers) // n_curves
    if n_rows == 0:
        raise ValueError('Не найдены числовые данные')

    array = numbers[: n_rows * n_curves].reshape(n_rows, n_curves)
    las.set_data(array)


def _read_las_file(text: str) -> lasio.LASFile:
    text = _sanitize_las_text(text)
    try:
        return lasio.read(text, ignore_header_errors=True)
    except ValueError:
        las = lasio.read(text, ignore_data=True, ignore_header_errors=True)
        _load_data_fallback(las, text)
        return las


def parse_las_file(raw_bytes: bytes) -> Tuple[pd.DataFrame, Dict, Dict]:
    """Парсинг LAS 2.0 через lasio. Возвращает (DataFrame, well_info, units)."""
    try:
        text = _decode_las_bytes(raw_bytes)
        las = _read_las_file(text)

        version = las.version.VERS.value if 'VERS' in las.version else None
        if version is not None and float(version) < 2.0:
        # if version != '2.0':
            raise ValueError(f'Поддерживается только LAS 2.0, получена версия {version}')

        df = _las_to_dataframe(las)
        if df.empty:
            raise ValueError('Файл не содержит данных')

        return df, _extract_well_info(las), _extract_units(las)
    except Exception as e:
        raise RuntimeError(f'Ошибка парсинга LAS: {e}') from e
