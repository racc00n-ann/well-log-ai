# sidebar.py

import streamlit as st
from core.utils import (
    correct_area,
    correct_company,
    clean_depth,
    handle_las_upload
)
from components.file_list import render_file_list
# Импортируем наш новый компонент:
from components.export_button import render_export_button
from ml_predictor.ui import run_prediction

def get_company_from_well_info(well_info):
    priority_fields = ['COMP', 'SRVC', 'SRVC_OC', 'WELL']
    for field in priority_fields:
        value = well_info.get(field)
        if value and value != '-' and value != '????':
            return value
    return '-'


def render_sidebar():
    st.markdown("### Управление файлами")

    uploader_key = f"sidebar_uploader_{st.session_state.sidebar_uploader_nonce}"
    uploaded_files = st.file_uploader(
        "Загрузить файлы",
        type="las",
        accept_multiple_files=True,
        label_visibility="visible",
        key=uploader_key,
    )

    handle_las_upload(uploaded_files, make_active_idx=0)

    if not st.session_state.all_files_data:
        return

    st.markdown("---")

    fid = st.session_state.active_file_id
    active_data = st.session_state.all_files_data[fid]

    df = active_data['df']
    well_info = active_data['well_info']
    dept_min = float(df['DEPT'].min())
    dept_max = float(df['DEPT'].max())

    slider_key = f"slider_{fid}"
    depth_raw = st.session_state.get(slider_key, (dept_min, dept_max))
    if not isinstance(depth_raw, (tuple, list)) or len(depth_raw) != 2:
        depth_range = (dept_min, dept_max)
    else:
        depth_range = (float(depth_raw[0]), float(depth_raw[1]))

    st.markdown("### Действия")

    if st.button(
        "Прогноз насыщения",
        key="predict_saturation_sidebar",
        type="primary",
        use_container_width=True,
    ):
        df_selected = df[(df['DEPT'] >= depth_range[0]) & (df['DEPT'] <= depth_range[1])]
        results = run_prediction(df_selected, well_info)
        if results is not None:
            st.session_state.all_files_data[fid]['prediction_results'] = results
            st.session_state.all_files_data[fid]['prediction_depth_range'] = depth_range
            st.session_state[slider_key] = depth_range
            st.rerun()

    render_export_button(active_data, fid, depth_range)

    st.markdown("---")
    st.markdown("### О скважине")

    well_name = well_info.get('WELL', '-')
    area_name = correct_area(well_info.get('FLD', '-'))
    company_name = correct_company(get_company_from_well_info(well_info))
    start_depth = clean_depth(well_info.get('STRT'))
    stop_depth = clean_depth(well_info.get('STOP'))
    well_date = well_info.get('DATE', '-')

    st.markdown(f"""
        <div style="font-size: 0.85rem; line-height: 1.4;">
            <b>Скважина:</b> {well_name} <br>
            <b>Площадь:</b> {area_name} <br>
            <b>Компания:</b> {company_name} <br>
            <b>Интервал:</b> {f'{start_depth:.1f}' if start_depth else '?'} — {f'{stop_depth:.1f}' if stop_depth else '?'} м <br>
            <b>Дата:</b> {well_date}
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    render_file_list()
    st.markdown("---")

    st.markdown("### Выбор кривых")
    units = active_data['units']
    available_curves = [col for col in df.columns if col != 'DEPT']
    curve_visibility = active_data['curve_visibility']

    if available_curves:
        cols = st.columns(2)
        for i, curve in enumerate(available_curves):
            col = cols[i % 2]
            checked = col.checkbox(
                f"{curve} [{units.get(curve, '?')}]",
                value=curve_visibility.get(curve, True),
                key=f"check_{fid}_{curve}",
            )
            active_data['curve_visibility'][curve] = checked

        active_data['selected_curves'] = [c for c in available_curves if active_data['curve_visibility'][c]]
        st.session_state.all_files_data[fid] = active_data
    else:
        st.warning("Нет кривых.")