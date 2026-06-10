# components/export_button.py
import streamlit as st
from core.utils import dataframe_to_excel_bytes
from ml_predictor.prediction import saturation_intervals_dataframe

def render_export_button(active_data, active_file_id, depth_range=None):
    """
    Компонент для экспорта данных скважины и результатов прогноза в Excel или CSV.
    """
    # Автоматически формируем базовое имя файла внутри компонента
    base_name = active_file_id.replace('.las', '')
    file_name = f"{base_name}_data.xlsx"

    df_to_save = active_data['df']
    prediction_results = active_data.get('prediction_results')

    if prediction_results is not None:
        df_to_save = df_to_save.copy()
        pred_export = prediction_results[
            ['Глубина', 'Класс', 'Данные_полные', 'Вероятность_Вода', 'Вероятность_Нефть', 'Вероятность_Смесь']
        ].rename(columns={'Класс': 'Прогноз_насыщения', 'Данные_полные': 'Данные_ГИС_полные'})

        df_to_save = df_to_save.merge(pred_export, left_on='DEPT', right_on='Глубина', how='left').drop(
            columns=['Глубина'])
        df_to_save['Прогноз_насыщения'] = df_to_save['Прогноз_насыщения'].fillna('Нет данных')
        df_to_save['Данные_ГИС_полные'] = df_to_save['Данные_ГИС_полные'].fillna(False)

    try:
        extra = None
        if prediction_results is not None:
            intervals_df = saturation_intervals_dataframe(prediction_results)
            extra = {'Интервалы_насыщения': intervals_df}

        excel_bytes = dataframe_to_excel_bytes(df_to_save, sheet_name='Данные_и_прогноз_по_точкам', extra_sheets=extra)

        st.download_button(
            label="Сохранить в Excel",
            data=excel_bytes,
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_excel_sidebar",
            use_container_width=True,
        )
    except ModuleNotFoundError:
        st.warning("Excel-модуль не найден. Доступен экспорт в CSV.")
        csv_name = f"{base_name}_data.csv"
        csv_bytes = df_to_save.to_csv(index=False).encode("utf-8-sig")

        st.download_button(
            label="Сохранить в CSV",
            data=csv_bytes,
            file_name=csv_name,
            mime="text/csv",
            key="download_csv_sidebar",
            use_container_width=True,
        )