"""Vegetation proximity from OSM, never a claim of actual absence."""
# Оценка использует только зелёные объекты, нанесённые на карту; отсутствие данных не доказывает отсутствие растений.

# Откладываем вычисление подсказок типов, чтобы использовать современный синтаксис.
from __future__ import annotations

# Point создаёт местоположение кандидата в метрической системе координат.
from shapely.geometry import Point
# unary_union объединяет контуры зелени для вычисления расстояния до ближайшей зоны.
from shapely.ops import unary_union

# Candidate задаёт структуру точки, которой будет назначена оценка.
from core.free_space import Candidate


# Возвращаем оценку удалённости каждой точки от нанесённой на карту зелени.
def green_deficit(candidates: list[Candidate], layers: dict) -> list[float]:
    # Собираем контуры парков/зелёных зон и деревьев, пропуская пустые записи карты.
    known = [g for key in ("green", "trees") for g in layers[key].geometry if g is not None and not g.is_empty]
    # Если карта ничего не сообщает о зелени, ставим всем нейтральное значение 0.5.
    if not known:
        # Нейтральная оценка означает неизвестность, а не подтверждённый дефицит зелени.
        return [0.5] * len(candidates)  # unknown coverage: neutral, not proof of a deficit
    # Объединяем всю известную зелень в одну геометрию, чтобы измерять до неё кратчайшее расстояние.
    union = unary_union(known)
    # Преобразуем расстояние в шкалу от 0 до 1, где 150 метров и дальше дают максимальный дефицит.
    return [min(1.0, Point(c.x, c.y).distance(union) / 150.0) for c in candidates]
