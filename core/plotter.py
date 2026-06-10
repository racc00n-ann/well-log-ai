# plotter.py
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core.constants import (
    CURVE_COLOR_MAP,
    DS_CURVE_MNEMS,
    LAS_NULL_VALUES,
    SATURATION_CLASS_U,
    SATURATION_COLORS,
    SATURATION_NAMES,
    SATURATION_PLOTLY_COLORSCALE,
)
from core.utils import parse_bit_size


def _curve_base_name(curve: str) -> str:
    return curve.split()[0].upper() if curve else ''


def _is_ds_curve(curve: str) -> bool:
    return _curve_base_name(curve) in DS_CURVE_MNEMS


def _clean_series(series: pd.Series) -> pd.Series:
    return series.replace(list(LAS_NULL_VALUES), np.nan)


def _sorted_prediction_arrays(results):
    depth = np.asarray(results['Глубина'].values, dtype=float)
    order = np.argsort(depth)
    return {
        'depth': depth[order],
        'predictions': np.asarray(results['Прогноз'].values, dtype=int)[order],
        'has_data': np.asarray(results['Данные_полные'].values, dtype=bool)[order],
        'prob_water': np.asarray(results['Вероятность_Вода'].values, dtype=float)[order],
        'prob_oil': np.asarray(results['Вероятность_Нефть'].values, dtype=float)[order],
        'prob_mix': np.asarray(results['Вероятность_Смесь'].values, dtype=float)[order],
    }


def _add_borehole_outline(fig, y_min, y_max, row=1, col=1, fill_color='white'):
    """Контур ствола; fill_color=None — только рамка поверх насыщения."""
    # Для fill_color=None (рамка поверх) используем полный диапазон [0.0, 1.0], иначе [0.2, 0.8]
    x_lo, x_hi = (0.0, 1.0) if not fill_color else (0.2, 0.8)

    fig.add_trace(
        go.Scatter(
            x=[x_lo, x_hi, x_hi, x_lo, x_lo],
            y=[y_min, y_min, y_max, y_max, y_min],
            fill='toself' if fill_color else 'none',
            fillcolor=fill_color,
            mode='lines' if not fill_color else None,
            line=dict(color='black', width=1.5 if not fill_color else 1),
            hoverinfo='skip',
            showlegend=False,
        ),
        row=row,
        col=col,
    )


def _add_borehole_track(fig, y_min, y_max, pred=None, row=1, col=1):
    """Трек скважины: без прогноза — пустой контур; с прогнозом — насыщение и рамка сверху."""
    if pred is not None and len(pred['depth']) >= 2:
        depth = pred['depth']
        y_mid = (depth[:-1] + depth[1:]) / 2.0
        z_sat = np.zeros((len(depth) - 1, 2), dtype=float)
        class_labels = []

        for i in range(len(depth) - 1):
            code = int(np.clip(pred['predictions'][i], 0, 4))
            z_sat[i, :] = SATURATION_CLASS_U[code]
            class_labels.append(SATURATION_NAMES.get(code, '—'))

        fig.add_trace(
            go.Heatmap(
                z=z_sat,
                x=[0.2, 0.8],
                y=y_mid,
                zmin=0,
                zmax=1,
                zsmooth=False,
                colorscale=SATURATION_PLOTLY_COLORSCALE,
                showscale=False,
                hovertemplate='%{y:.1f} м<br>%{customdata}<extra></extra>',
                customdata=[[lbl, lbl] for lbl in class_labels],
            ),
            row=row,
            col=col,
        )

        # Добавляем элементы насыщения в общую сквозную легенду
        for code, name in SATURATION_NAMES.items():
            fig.add_trace(
                go.Scatter(
                    x=[None], y=[None],
                    mode='markers',
                    marker=dict(color=SATURATION_COLORS[code], size=11, symbol='square'),
                    name=name,
                    showlegend=True,
                ),
                row=row,
                col=col,
            )

    _add_borehole_outline(fig, y_min, y_max, row=row, col=col, fill_color=None)
    fig.update_xaxes(range=[0, 1], showticklabels=False, row=row, col=col)


def _add_probability_track(fig, pred, row=1, col=1):
    depth = pred['depth']
    n = len(depth)
    if n < 2:
        fig.update_xaxes(visible=False, row=row, col=col)
        return

    W = 48
    y_mid = (depth[:-1] + depth[1:]) / 2.0
    z_prob = np.full((n - 1, W), SATURATION_CLASS_U[0], dtype=float)
    x_prob = np.linspace(0.0, 1.0, W)

    for i in range(n - 1):
        if pred['predictions'][i] == 4:
            z_prob[i, :] = SATURATION_CLASS_U[4]
            continue
        if not pred['has_data'][i]:
            z_prob[i, :] = SATURATION_CLASS_U[0]
            continue

        w, o, m = pred['prob_water'][i], pred['prob_oil'][i], pred['prob_mix'][i]
        t = w + o + m
        if t > 1e-9:
            w, o, m = w / t, o / t, m / t

        a = min(W, int(W * w))
        b = min(W, int(W * (w + o)))
        z_prob[i, :a] = SATURATION_CLASS_U[1]
        z_prob[i, a:b] = SATURATION_CLASS_U[2]
        z_prob[i, b:] = SATURATION_CLASS_U[3]

    fig.add_trace(
        go.Heatmap(
            z=z_prob,
            x=x_prob,
            y=y_mid,
            zmin=0,
            zmax=1,
            colorscale=SATURATION_PLOTLY_COLORSCALE,
            showscale=False,
            hovertemplate='%{y:.1f} м<br>Вероятности<extra></extra>',
        ),
        row=row,
        col=col,
    )
    fig.update_xaxes(
        title=dict(text='вода / нефть / смесь', font=dict(size=10), standoff=25),
        range=[0, 1],
        side='top',
        showline=True,
        linecolor='black',
        mirror='all',
        linewidth=1,
        row=row,
        col=col,
    )


def _add_line_trace(fig, x, y, name, color, axis_title, col_idx, row=1):
    """Универсальная функция для добавления линейных трейсов (кривых ГИС, долота) и настройки осей X."""
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode='lines',
            line=dict(color=color, width=1.5),
            name=name,
            showlegend=True,
            hovertemplate=f'Гл: %{{y:.2f}} м<br>{name}: %{{x:.4g}}<extra></extra>',
        ),
        row=row,
        col=col_idx,
    )
    fig.update_xaxes(
        title=dict(text=axis_title, font=dict(size=11), standoff=25),
        side='top',
        gridcolor='rgba(200, 200, 200, 0.3)',
        tickfont=dict(size=10),
        showline=True,
        linecolor='black',
        mirror=True,
        linewidth=1,
        row=row,
        col=col_idx,
    )


def _add_gis_curves(fig, df_filtered, selected_curves, units, first_col, well_info=None, row=1):
    """Добавление кривых ГИС на соответствующие треки."""
    bit_size = parse_bit_size(well_info or {})
    dept = df_filtered['DEPT'].values

    for i, curve in enumerate(selected_curves):
        col_idx = first_col + i
        unit = units.get(curve, 'у.е.')

        if _is_ds_curve(curve) and bit_size is not None:
            # 1. Добавляем сам калипер (DS)
            _add_line_trace(
                fig, x=_clean_series(df_filtered[curve]), y=dept,
                name=f"{curve} ({unit})", color=CURVE_COLOR_MAP.get('DS', 'brown'),
                axis_title=unit, col_idx=col_idx, row=row
            )
            # 2. Добавляем размер долота (в тот же трек)
            _add_line_trace(
                fig, x=[bit_size, bit_size], y=[dept.min(), dept.max()],
                name=f'Диаметр долота ({bit_size:.3f} м)', color='black',
                axis_title=unit, col_idx=col_idx, row=row
            )
        else:
            # Добавление стандартной кривой ГИС
            base_name = _curve_base_name(curve)
            color = CURVE_COLOR_MAP.get(base_name, f'C{i}')
            _add_line_trace(
                fig, x=_clean_series(df_filtered[curve]), y=dept,
                name=f"{curve} ({unit})", color=color,
                axis_title=unit, col_idx=col_idx, row=row
            )


@st.cache_data
def plot_well_log(df, well_info, units, selected_curves, depth_range=None, prediction_results=None):
    """Единый профиль скважины со структурированной многоколоночной легендой.
    Работает даже если выбранные кривые отсутствуют.
    """
    if 'DEPT' not in df.columns:
        return None

    y_min, y_max = depth_range if depth_range else (df['DEPT'].min(), df['DEPT'].max())
    df_filtered = df[(df['DEPT'] >= y_min) & (df['DEPT'] <= y_max)].copy()
    has_prediction = prediction_results is not None and len(prediction_results) > 0

    # Безопасно инициализируем список кривых, если пришел None
    curves_to_plot = selected_curves if selected_curves else []

    # 1. Динамическая сборка структуры колонок
    # ТЕРМИН СОГЛАСОВАН С БЛОК-СХЕМОЙ: Везде используем "Ствол скважины"
    titles = ['<b>Ствол скважины</b>']
    widths = [0.4]  # Начальный вес для трека скважины

    # Добавляем колонки для кривых ГИС (если они выбраны)
    for c in curves_to_plot:
        titles.append(f'<b>{c}</b>')
        widths.append(1.0)

    # Добавляем трек вероятностей (если есть прогноз)
    if has_prediction:
        titles.append('<b>Вероятности</b>')
        # Если кривых нет, делаем трек вероятностей шире для красивого баланса
        widths.append(0.42 if curves_to_plot else 0.8)

    # 2. Создаем сабплоты с динамическим числом колонок
    fig = make_subplots(
        rows=1, cols=len(titles), shared_yaxes=True,
        horizontal_spacing=0.03 if not curves_to_plot else 0.02,
        column_widths=widths, subplot_titles=titles,
    )

    # 3. Отрисовка компонентов
    pred = _sorted_prediction_arrays(prediction_results) if has_prediction else None

    # Трек 1: Всегда первый (Ствол скважины)
    _add_borehole_track(fig, y_min, y_max, pred=pred, col=1)

    # Треки ГИС: Отрисовываем только если они есть
    if curves_to_plot:
        _add_gis_curves(fig, df_filtered, curves_to_plot, units, first_col=2, well_info=well_info)

    # Трек вероятностей: Всегда последний (если есть прогноз)
    if has_prediction:
        _add_probability_track(fig, pred, col=len(titles))

    # 4. Общие настройки осей Y
    fig.update_yaxes(
        range=[y_max, y_min], gridcolor='rgba(200, 200, 200, 0.3)',
        title_text='Глубина, м', row=1, col=1
    )
    fig.update_yaxes(showline=True, linecolor='black', mirror='all', linewidth=1.5, row=1, col='all')

    # Скрываем подписи глубин для всех колонок, кроме первой
    for c in range(2, len(titles) + 1):
        fig.update_yaxes(showticklabels=False, row=1, col=c)

    title_well = well_info.get('WELL', 'Неизвестно')
    title_text = f"Скважина: {title_well}" + (" — прогноз насыщения" if has_prediction else "")

    fig.update_layout(
        title={'text': title_text, 'y': 0.98, 'x': 0.5, 'xanchor': 'center', 'yanchor': 'top', 'font': dict(size=20)},
        height=950,
        showlegend=True,
        template='plotly_white',
        margin=dict(t=150, b=180, l=60, r=20),
        hovermode='y unified',
        legend=dict(
            orientation='h', yanchor='top', y=-0.1, x=0.0, xanchor='left', traceorder='normal',
            entrywidth=180, entrywidthmode='pixels',
        )
    )

    for ann in fig.layout.annotations:
        ann.update(y=1.09, font=dict(size=14, color='#4f4f4f'))

    return fig