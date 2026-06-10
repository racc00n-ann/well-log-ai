# utils.py
from core.constants import AREAS, COMPANIES
import re
from io import BytesIO
import pandas as pd

def parse_bit_size(well_info: dict) -> float | None:
    """Bit Size (BS) из блока Parameter LAS, в метрах."""
    if not well_info:
        return None
    for key, raw in well_info.items():
        if key.strip().upper() != 'BS':
            continue
        text = str(raw).strip().split(':')[0].strip()
        match = re.search(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', text)
        if not match:
            continue
        value = float(match.group())
        if value > 0 and abs(value + 9999.0) > 1e-3:
            return value
    return None


def clean_key(text: str) -> str:
    """Приводит текст к ключу: убирает пробелы, переводит в верхний регистр."""
    if not text or not isinstance(text, str):
        return ""
    return text.strip().upper().replace(" ", "").replace("-", "").replace("_", "").replace(".", "")

def correct_area(text: str) -> str:
    """Исправляет название площади."""
    if not text:
        return text
    return AREAS.get(clean_key(text), text)

def correct_company(text: str) -> str:
    """Исправляет название компании."""
    if not text:
        return text
    return COMPANIES.get(clean_key(text), text)

def clean_depth(value):
    """
    Извлекает число из строки вида 'M 1051.00', ' 1051.00 m', 'Depth: 1051' и т.п.
    Возвращает float или None.
    """
    if not value:
        return None

    # Приводим к строке, на случай, если пришёл float или int
    value = str(value).strip()

    # Ищем первое число (целое или дробное) в строке
    match = re.search(r"[-+]?\d*\.?\d+", value.replace(',', '.'))
    if match:
        try:
            return float(match.group())
        except (ValueError, TypeError):
            return None
    return None

def dataframe_to_excel_bytes(df, sheet_name='Sheet1', index=False, extra_sheets=None):
    """Возвращает Excel-файл как bytes для скачивания через Streamlit.

    extra_sheets: dict {имя_листа: DataFrame} — дополнительные листы (например интервалы).
    Имена листов обрезаются до 31 символа (ограничение Excel).
    """
    output = BytesIO()

    def _safe_name(name):
        s = str(name) if name is not None else 'Sheet'
        return s[:31] if len(s) > 31 else s

    with pd.ExcelWriter(output) as writer:
        df.to_excel(writer, sheet_name=_safe_name(sheet_name), index=index)
        if extra_sheets:
            for name, sheet_df in extra_sheets.items():
                sheet_df.to_excel(writer, sheet_name=_safe_name(name), index=index)
    return output.getvalue()


import streamlit as st
from core.las_parser import parse_las_file


def create_file_session_data(current_bytes: bytes, df: pd.DataFrame, well_info: dict, units: dict) -> dict:
    """
    Формирует единую структуру данных для сохранения LAS-файла в st.session_state.
    """
    available_curves = [col for col in df.columns if col != 'DEPT']
    return {
        'bytes': current_bytes,
        'df': df,
        'well_info': well_info,
        'units': units,
        'curve_visibility': {c: True for c in available_curves},
        'selected_curves': available_curves[:3],  # По умолчанию выбираем первые 3 кривые
        'prediction_results': None,
        'prediction_depth_range': None,
    }


def handle_las_upload(uploaded_files, make_active_idx: int = 0) -> None:
    """
    Полностью обрабатывает список загруженных файлов, парсит их и обновляет состояние.
    make_active_idx: 0 для выбора первого файла (боковая панель),
                    -1 для выбора последнего загруженного файла (главный экран).
    """
    if not uploaded_files:
        return

    added_new = False
    for uploaded_file in uploaded_files:
        file_id = uploaded_file.name
        if file_id not in st.session_state.all_files_data:
            try:
                current_bytes = uploaded_file.getvalue()
                df, well_info, units = parse_las_file(current_bytes)

                # Создаем стандартизированную структуру данных
                st.session_state.all_files_data[file_id] = create_file_session_data(
                    current_bytes, df, well_info, units
                )
                added_new = True
            except Exception as e:
                st.error(f"Ошибка при парсинге {file_id}: {e}")

    # Логика изменения активного файла и перезапуска страницы
    if added_new:
        if not st.session_state.active_file_id:
            keys = list(st.session_state.all_files_data.keys())
            st.session_state.active_file_id = keys[make_active_idx]
        st.session_state.sidebar_uploader_nonce += 1
        st.rerun()
    elif st.session_state.all_files_data:
        names = [uf.name for uf in uploaded_files]
        if names and all(n in st.session_state.all_files_data for n in names):
            st.session_state.sidebar_uploader_nonce += 1
            st.rerun()
