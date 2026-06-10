# file_list.py
import streamlit as st

def render_file_list():
    if not st.session_state.all_files_data:
        return

    file_ids = list(st.session_state.all_files_data.keys())

    st.markdown("### Загруженные файлы")

    current = (
        st.session_state.active_file_id
        if st.session_state.active_file_id in file_ids
        else file_ids[0]
    )
    idx = file_ids.index(current)

    choice = st.selectbox(
        "Текущий файл",
        file_ids,
        index=idx,
        key="active_file_selectbox",
        label_visibility="collapsed",
    )
    if choice != st.session_state.active_file_id:
        st.session_state.active_file_id = choice
        st.rerun()

    to_delete = st.multiselect(
        "Отметьте файлы для удаления",
        options=file_ids,
        key="files_marked_for_deletion",
        placeholder="Выберите файлы..."
    )

    col_del_sel, col_del_all = st.columns(2)
    with col_del_sel:
        if st.button(
            "❌",
            key="btn_delete_selected_files",
            disabled=len(to_delete) == 0,
            use_container_width=True,
            help="Удалить выбранные файлы из списка"
        ):
            for fid in to_delete:
                st.session_state.all_files_data.pop(fid, None)
            remaining = list(st.session_state.all_files_data.keys())
            if not remaining:
                st.session_state.active_file_id = None
            elif st.session_state.active_file_id not in st.session_state.all_files_data:
                st.session_state.active_file_id = remaining[0]
            st.rerun()
    with col_del_all:
        if st.button(
            "🗑️",
            key="btn_delete_all_files",
            use_container_width=True,
            help="Полностью очистить весь список файлов"
        ):
            st.session_state.all_files_data = {}
            st.session_state.active_file_id = None
            st.rerun()
