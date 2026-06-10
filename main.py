# main.py
# streamlit run main.py

import streamlit as st
from components import sidebar, main_content

st.set_page_config(layout="wide", page_title="Прогноз насыщения коллекторов")

def load_css(file_name):
    with open(file_name, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

css_files = ["styles/base.css", "styles/sidebar.css", "styles/content.css"]
for css in css_files:
    load_css(css)

# Инициализация session_state
if 'all_files_data' not in st.session_state:
    st.session_state.all_files_data = {}
if 'active_file_id' not in st.session_state:
    st.session_state.active_file_id = None
if 'first_run' not in st.session_state:
    st.session_state.first_run = True
if 'sidebar_uploader_nonce' not in st.session_state:
    st.session_state.sidebar_uploader_nonce = 0

# Кастомный отступ для контента, если файл выбран + глобальное скрытие хедера
if st.session_state.active_file_id is not None:
    st.markdown("""
        <style>
            section[data-testid="stMain"] {
                margin-left: 300px !important;
                width: calc(100% - 300px) !important;
            }
            header[data-testid="stHeader"] {
                display: none !important;
            }
            div[data-testid="stAppViewBlockContainer"] {
                padding-top: 0rem !important; 
            }
        </style>
    """, unsafe_allow_html=True)
else:
    # Если файл не выбран, панель все равно скрываем, чтобы не мешалась
    st.markdown("""
        <style>
            header[data-testid="stHeader"] {
                display: none !important;
            }
            div[data-testid="stAppViewBlockContainer"] {
                padding-top: 0rem !important;
            }
        </style>
    """, unsafe_allow_html=True)

# Отображаем сайдбар только если есть загруженные файлы
if st.session_state.all_files_data:
    with st.sidebar:
        sidebar.render_sidebar()
else:
    st.session_state.first_run = False

# Отрисовка основного контента (он сам разберется, пустой state или нет)
main_content.render_main_content()

with st.expander("Посмотреть Session State"):
    st.write(st.session_state)