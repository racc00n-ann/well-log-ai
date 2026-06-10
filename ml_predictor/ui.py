# ui.py

"""
Streamlit: запуск прогноза и отображение таблиц/статистики (график — в plotter.plot_well_log).
"""

import time

import streamlit as st


from ml_predictor.features import check_required_features, map_las_columns
from ml_predictor.model_loader import load_model_cached
from ml_predictor.prediction import predict_saturation, saturation_intervals_dataframe

"""Пути к артефактам обученной модели."""

import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(_PROJECT_ROOT, 'models')
MODEL_PATH = os.path.join(MODEL_DIR, 'saturation_model.joblib')
FEATURES_PATH = os.path.join(MODEL_DIR, 'feature_columns.joblib')


def render_prediction_stats(results):
    """Статистика, интервалы и таблица по глубинам (без графика — он на том же профиле скважины)."""
    total = len(results)
    with_data = results['Данные_полные'].sum()
    without_data = total - with_data

    st.markdown("### Статистика прогноза")

    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.info(f"**Всего точек:** {total}")
    with col_info2:
        coverage = with_data / total * 100 if total > 0 else 0
        if coverage == 100:
            st.success(f"**Полный комплекс ГИС:** {with_data} ({coverage:.1f}%)")
        elif coverage > 50:
            st.warning(f"**Полный комплекс ГИС:** {with_data} ({coverage:.1f}%)")
        else:
            st.error(f"**Полный комплекс ГИС:** {with_data} ({coverage:.1f}%)")

    if without_data > 0:
        st.caption(f"Точек без полного комплекса ГИС (прогноз не выполнен): {without_data}")

    st.markdown("---")

    results_with_data = results[results['Данные_полные']]

    if len(results_with_data) > 0:
        nc_count = (results_with_data['Прогноз'] == 4).sum()
        collector = results_with_data[results_with_data['Прогноз'].isin([1, 2, 3])]
        n_coll = len(collector)

        col1, col2, col3, col4 = st.columns(4)
        water_count = (collector['Прогноз'] == 1).sum() if n_coll else 0
        oil_count = (collector['Прогноз'] == 2).sum() if n_coll else 0
        mix_count = (collector['Прогноз'] == 3).sum() if n_coll else 0

        with col1:
            st.metric("Вода", f"{water_count} ({water_count / n_coll * 100:.1f}%)" if n_coll else "0 (—)")
        with col2:
            st.metric("Нефть", f"{oil_count} ({oil_count / n_coll * 100:.1f}%)" if n_coll else "0 (—)")
        with col3:
            st.metric("Водонефтяная смесь", f"{mix_count} ({mix_count / n_coll * 100:.1f}%)" if n_coll else "0 (—)")
        with col4:
            st.metric(
                "Неколлектор",
                f"{nc_count} ({nc_count / len(results_with_data) * 100:.1f}%)",
            )

        st.markdown("### Интервалы насыщения")
        interval_df = saturation_intervals_dataframe(results)
        if not interval_df.empty:
            st.dataframe(interval_df, use_container_width=True, hide_index=True)
        else:
            st.info("Интервалы не определены")
    else:
        st.warning("Нет точек с полным комплексом ГИС для отображения статистики")

    with st.expander("Подробные результаты по глубинам"):
        display_df = results[['Глубина', 'Класс', 'Данные_полные',
                              'Вероятность_Вода', 'Вероятность_Нефть',
                              'Вероятность_Смесь']].copy()
        display_df.columns = ['Глубина, м', 'Насыщение', 'Данные',
                              'P(Вода)', 'P(Нефть)', 'P(Смесь)']
        display_df['Данные'] = display_df['Данные'].apply(lambda x: '✅' if x else '❌')

        for col in ['P(Вода)', 'P(Нефть)', 'P(Смесь)']:
            display_df[col] = display_df.apply(
                lambda row, c=col: (
                    '-'
                    if row['Данные'] != '✅' or row['Насыщение'] == 'Неколлектор'
                    else f"{row[c]:.2%}"
                ),
                axis=1,
            )

        st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)


def render_prediction_results(results, df, well_info):
    """Устаревший вызов: только статистика (df и well_info не используются)."""
    del df, well_info
    render_prediction_stats(results)


def run_prediction(df, well_info):
    """
    Запуск прогноза для текущего файла.

    Returns:
        DataFrame с прогнозами или None при ошибке.
    """
    start = time.perf_counter()
    try:
        model_bundle, feature_columns, thresholds = load_model_cached()
    except ImportError as e:
        st.error(str(e))
        st.code("pip install -r requirements.txt", language="bash")
        return None

    if model_bundle is None:
        st.error(f"Модель не найдена: {MODEL_PATH}")
        st.info("Положите файлы saturation_model.joblib и feature_columns.joblib в папку models/.")
        return None

    if not feature_columns:
        st.error("Список признаков модели не найден (feature_columns.joblib или поле feature_columns в bundle).")
        return None

    mapped_df = map_las_columns(df)
    missing = check_required_features(mapped_df, feature_columns)

    if missing:
        st.error(f"В файле отсутствуют необходимые каротажи: {', '.join(missing)}")
        st.info("""
        **Необходимые методы каротажа:**
        - GR (гамма каротаж)
        - NGR (нейтрон-гамма каротаж)
        - BK (боковой каротаж)
        - DS (диаметр скважины)
        - DT (акустический каротаж)
        """)
        return None

    with st.spinner("Выполняется прогноз..."):
        results, error = predict_saturation(
            df, model_bundle, feature_columns, thresholds, well_info=well_info,
        )

    if error:
        st.error(f"Ошибка прогноза: {error}")
        return None

    total = len(results)
    with_data = results['Данные_полные'].sum()
    if with_data < total:
        st.info(f"Прогноз выполнен для {with_data} из {total} точек (полный комплекс ГИС)")

    elapsed = time.perf_counter() - start
    st.info(f"Время выполнения прогноза: {elapsed:.2f} сек.")
    return results
