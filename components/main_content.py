# main_content.py
import streamlit as st
from core.plotter import plot_well_log
from ml_predictor.ui import render_prediction_stats
from core.utils import handle_las_upload  # <-- Подключили общую функцию


def render_main_content():
    # ЕСЛИ ФАЙЛОВ НЕТ — показываем красивый стартовый экран по центру
    if not st.session_state.all_files_data:
        empty_col_left, uploader_col, empty_col_right = st.columns([1, 2, 1])

        with uploader_col:
            st.markdown("""
                <div class="welcome-container">
                   <h1>Добро пожаловать!</h1>
                   <p>Система ML-интерпретации данных ГИС для определения характера насыщения коллекторов.</p>
                </div>
            """, unsafe_allow_html=True)

            st.caption("Загрузите файлы каротажа (.las v2.0), чтобы построить планшет и запустить прогноз насыщения:")

            uploaded_files = st.file_uploader(
                "Перетащите файлы сюда",
                type="las",
                accept_multiple_files=True,
                key="main_uploader_unique",
                label_visibility="collapsed"
            )

            if uploaded_files:
                st.session_state.first_run = False
                # Передаем управление в utils.py, -1 означает "сделать активным последний добавленный файл"
                handle_las_upload(uploaded_files, make_active_idx=-1)

    # ЕСЛИ ФАЙЛЫ ЕСТЬ — работаем с выбранным файлом
    else:
        if st.session_state.active_file_id and st.session_state.active_file_id in st.session_state.all_files_data:
            active_data = st.session_state.all_files_data[st.session_state.active_file_id]
            df = active_data['df']
            well_info = active_data['well_info']
            selected_curves = active_data['selected_curves']
            units = active_data['units']
            prediction_results = active_data.get('prediction_results')

            fid = st.session_state.active_file_id
            slider_key = f"slider_{fid}"

            try:
                dept_min, dept_max = float(df['DEPT'].min()), float(df['DEPT'].max())
                stored_dr = active_data.get('prediction_depth_range')
                if slider_key not in st.session_state:
                    if stored_dr and prediction_results is not None:
                        st.session_state[slider_key] = (
                            float(stored_dr[0]),
                            float(stored_dr[1]),
                        )
                    else:
                        st.session_state[slider_key] = (dept_min, dept_max)

                depth_range = st.slider(
                    "Выберите интервал глубин, м",
                    min_value=dept_min,
                    max_value=dept_max,
                    step=1.0,
                    format="%.0f",
                    key=slider_key,
                )
            except Exception as e:
                st.error(f"Ошибка при расчете глубин: {e}")
                depth_range = (0, 0)

            pred_view = None
            if prediction_results is not None:
                mask = (
                        (prediction_results['Глубина'] >= depth_range[0])
                        & (prediction_results['Глубина'] <= depth_range[1])
                )
                pred_view = prediction_results[mask]

            try:
                fig = plot_well_log(
                    df,
                    well_info,
                    units,
                    selected_curves,
                    depth_range=depth_range,
                    prediction_results=pred_view,
                )
                if fig is not None:
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"Ошибка при построении графика: {e}")

            if pred_view is not None and len(pred_view) > 0:
                st.markdown("---")
                render_prediction_stats(pred_view)
            elif prediction_results is None:
                st.caption(
                    "Нажмите «Прогноз насыщения» в боковой панели, чтобы добавить "
                    "треки насыщения и вероятностей к этому профилю."
                )

        else:
            st.info("Выберите скважину или файл в списке на боковой панели для отображения планшета.")