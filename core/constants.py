# constants.py
# 
# """Константы приложения: каротаж, LAS, насыщение, метаданные скважин."""

# --- LAS / признаки ML ---

LAS_TO_FEATURE_MAP = {
    'GR': 'GR', 'GK': 'GR', 'GAMMA': 'GR',
    'NGR': 'NGR', 'NKTD': 'NGR', 'NPHI': 'NGR', 'NK': 'NGR',
    'BK': 'BK', 'LLD': 'BK', 'LLS': 'BK', 'RDEEP': 'BK', 'RT': 'BK',
    'DS': 'DS', 'CALI': 'DS', 'CAL': 'DS',
    'DT': 'DT', 'AC': 'DT', 'SONIC': 'DT',
    'IK': 'IK', 'ILD': 'IK', 'RILD': 'IK',
    'PZ': 'PZ', 'RSFL': 'PZ', 'RMLL': 'PZ',
    'SP': 'SP', 'SSP': 'SP',
    'DEPT': 'depth_carriage',
}

BASE_FEATURES = ['BK', 'DS', 'DT', 'GR', 'NGR']

# Коды пропусков в LAS
LAS_NULL_VALUES = (-9999.0, -999.25)

# --- Визуализация каротажа ---

CURVE_COLOR_MAP = {
    'GR': 'green',
    'NGR': 'limegreen',
    'BK': 'red',
    'IK': 'orange',
    'SP': 'purple',
    'PZ': 'magenta',
    'DT': 'blue',
    'DS': 'brown',
}

# Мнемоники диаметра скважины (для отдельного трека DS)
DS_CURVE_MNEMS = frozenset({'DS', 'CALI', 'CAL'})

# --- Классы насыщения ---

SATURATION_COLORS = {
    0: '#d3d3d3',  # Нет данных
    1: '#3498db',  # Вода #85c1e9
    2: '#f39c12',  # Нефть
    3: '#27ae60',  # Вода+Нефть
    4: '#6d6d6d',  # Неколлектор (по ГИС)
}

SATURATION_NAMES = {
    0: 'Нет данных',
    1: 'Вода',
    2: 'Нефть',
    3: 'Вода+Нефть',
    4: 'Неколлектор',
}

# Классы 0–4 → позиции на шкале Plotly heatmap (0–1)
SATURATION_CLASS_U = {0: 0.1, 1: 0.3, 2: 0.5, 3: 0.7, 4: 0.9}

SATURATION_PLOTLY_COLORSCALE = [
    [0.0, SATURATION_COLORS[0]],
    [0.199, SATURATION_COLORS[0]],
    [0.2, SATURATION_COLORS[1]],
    [0.399, SATURATION_COLORS[1]],
    [0.4, SATURATION_COLORS[2]],
    [0.599, SATURATION_COLORS[2]],
    [0.6, SATURATION_COLORS[3]],
    [0.799, SATURATION_COLORS[3]],
    [0.8, SATURATION_COLORS[4]],
    [1.0, SATURATION_COLORS[4]],
]

# Пороги вероятностей по умолчанию (нефть / смесь — ниже)
DEFAULT_PREDICTION_THRESHOLDS = {
    'water': 0.5,
    'oil': 0.25,
    'mix': 0.25,
}

# Правила маски неколлектора (noncollector_mask): обновленные под непрерывные петрофизические коэффициенты.
# Идеально настроено под терригенный палеозой (Арланское месторождение).
NONCOLLECTOR_RULES = {
    'v_shale_clay': 0.38,       # Критический объем глины по Ларионову (38%). Выше этого — неколлектор.
    'i_dt_tight': 0.08,        # Критический акустический индекс плотности. Ниже 8% пористости матрицы — плотняк.
    'r_relative_clay': 1.3,    # Макс. контрастность к глинам для заглинизированных пластов (БК / R_глины).
    'r_relative_tight': 5.0,   # Мин. контрастность для плотных разностей (БК / R_глины должно быть > 5).
    'washout_cm': 1.5,         # Превышение диаметра ствола (каверна) над долотом на 1.5 см и более.
    'tight_hole_cm': 0.8,      # Допуск номинального ствола (отклонение каверномера от долота менее 8 мм).
    'min_nc_run_points': 3,    # Фильтрация микро-прослоев (убирает одиночные "шумящие" точки).
}
# --- Метаданные скважин ---

AREAS = {
    'VAYATSKAYA': 'Вятская',
    'VYATSKAYA': 'Вятская',
}

COMPANIES = {
    'YDMYRTGEOLOGIA': 'Удмуртгеология',
    'UDMURTGEOLOGIA': 'Удмуртгеология',
    'АРЛАНСКАЯПГК': 'Арланская ПГК',
    'ARLANSKAYAPGK': 'Арланская ПГК',
}

UNIT_TRANSLATIONS = {
    'OHMM': 'Ом·м',
    'MV': 'мВ',
    'M': 'м',
    'MCS': 'мкс/м',
    'MSM/M': 'мСм/м',
    'UE': 'у.е.',
    'MCR/H': 'мкР/ч',
}
