"""Dimensionless relative heat-load proxy, not measured air temperature."""
# Здесь рассчитывается сравнительный индекс тепловой нагрузки, а не температура в градусах.

# Откладываем вычисление типов, чтобы использовать современный синтаксис подсказок.
from __future__ import annotations

# math нужен для расчёта расстояния между точками.
import math

# Point задаёт местоположение кандидата для пространственных вычислений.
from shapely.geometry import Point
# Объединение геометрий ускоряет последующие проверки пересечений и расстояний.
from shapely.ops import unary_union

# Импортируем настройки модели: радиусы в метрах и веса влияния разных типов окружения.
from config import (CANOPY_RADIUS_M, HEAT_BASE, HEAT_BUILDING_WEIGHT, HEAT_CONTEXT_RADIUS_M,
                    # Вес зелени уменьшает индекс, а вес дороги и радиус прокси задают её влияние.
                    HEAT_GREEN_WEIGHT, HEAT_ROAD_WEIGHT, MAPPED_TREE_PROXY_RADIUS_M,
                    # Доля отклика под кроной задаёт сценарное снижение относительного индекса.
                    SHADE_INDEX_RESPONSE)
# Candidate содержит координаты и поле относительной оценки тепла.
from core.free_space import Candidate


# Оцениваем тепловой контекст всех кандидатов по зданиям, дорогам и зелени вокруг них.
def heat_scores(candidates: list[Candidate], layers: dict) -> list[float]:
    # Объединяем контуры зданий, игнорируя отсутствующие и пустые геометрии.
    buildings = unary_union([g for g in layers["buildings"].geometry if g is not None and not g.is_empty])
    # Аналогично собираем дорожную сеть, которая может усиливать тепловую нагрузку.
    roads = unary_union([g for g in layers["roads"].geometry if g is not None and not g.is_empty])
    # Получаем слой деревьев, если он присутствует в наборе карт.
    tree_frame=layers.get("trees")
    # Каждое нанесённое дерево расширяем условным радиусом, чтобы учитывать его окрестность.
    tree_geometries=[] if tree_frame is None else [g.buffer(MAPPED_TREE_PROXY_RADIUS_M) for g in tree_frame.geometry if g is not None and not g.is_empty]
    # Объединяем зелёные зоны и условные области деревьев в общий слой растительности.
    green = unary_union([g for g in layers["green"].geometry if g is not None and not g.is_empty]+tree_geometries)
    # Здесь будут оценки для каждой точки-кандидата в том же порядке, что и входной список.
    result = []
    # Считаем окружение каждой кандидатной точки отдельно.
    for c in candidates:
        # Создаём геометрию самой точки из её координат в метрах.
        p = Point(c.x, c.y)
        # Диск задаёт локальный район анализа вокруг точки.
        disk = p.buffer(HEAT_CONTEXT_RADIUS_M)
        # Доля площади диска, занятая зданиями; если зданий нет, доля равна нулю.
        built = buildings.intersection(disk).area / disk.area if not buildings.is_empty else 0.0
        # Доля диска с зеленью; это снижает итоговую оценку тепловой нагрузки.
        vegetation = green.intersection(disk).area / disk.area if not green.is_empty else 0.0
        # Близкая дорога даёт больший вклад; дальше радиуса влияния вклад становится нулевым.
        road = max(0.0, 1.0 - p.distance(roads) / HEAT_CONTEXT_RADIUS_M) if not roads.is_empty else 0.0
        # Складываем базу и взвешенные факторы, затем ограничиваем результат диапазоном 0–1.
        result.append(min(1.0, max(0.0, HEAT_BASE + HEAT_BUILDING_WEIGHT * built
                                     # Вклад дороги прибавляется, вклад растительности вычитается.
                                     + HEAT_ROAD_WEIGHT * road - HEAT_GREEN_WEIGHT * vegetation)))
    # Список соответствует исходным кандидатам и содержит безразмерные индексы от 0 до 1.
    # Один безразмерный индекс от 0 до 1 возвращается для каждой входной точки.
    return result


# Оцениваем сценарный индекс после появления крон у выбранных деревьев.
def after_heat_scores(candidates: list[Candidate], selected: list[Candidate]) -> list[float]:
    # Докстрока уточняет, что ниже оценивается сценарий, а не измеренная погода.
    """Scenario-only exposure index after shade inside assumed canopy footprints."""
    # В этом списке будут оценки тепла после добавления выбранных деревьев.
    result=[]
    # Для каждой точки оцениваем влияние ближайшей кроны.
    for candidate in candidates:
        # Влияние линейно убывает до нуля на расстоянии радиуса кроны; минимум задаёт нулевое влияние.
        influence=max([0.0]+[1.0-math.hypot(candidate.x-tree.x,candidate.y-tree.y)/CANOPY_RADIUS_M for tree in selected])
        # Уменьшаем исходное тепло пропорционально влиянию кроны и коэффициенту реакции модели.
        result.append(candidate.heat*(1.0-SHADE_INDEX_RESPONSE*influence))
    # Возвращаем список с оценкой для каждой исходной точки.
    return result


# Считаем исходный и сценарный тепловые индексы с весом площади участка.
def scenario_area_heat_index(candidates:list[Candidate],selected:list[Candidate],study_area)->tuple[float,float]:
    # Докстрока отмечает вес площади и модельное допущение о влиянии крон.
    """Area-weighted scenario using local heat scores and assumed canopy response."""
    # Среднее по кандидатам служит исходным относительным индексом до посадки.
    baseline=sum(c.heat for c in candidates)/len(candidates) if candidates else 0.0
    # При отсутствии корректной площади или выбранных деревьев сценарий совпадает с исходным.
    if study_area is None or study_area.area<=0 or not selected:
        # Без участка или деревьев невозможно получить отличающийся сценарный результат.
        return baseline,baseline
    # covered отслеживает уже учтённые кроны, исключая двойной подсчёт их перекрытий.
    covered=None
    # Сумма «тепловая оценка × новая затенённая площадь» нужна для взвешенного эффекта.
    weighted_shade=0.0
    # Рассматриваем сначала более горячие точки, чтобы порядок расчёта был устойчивым.
    for tree in sorted(selected,key=lambda c:(-c.heat,c.id)):
        # Ограничиваем круг кроны границей участка и получаем площадь в квадратных метрах.
        canopy=Point(tree.x,tree.y).buffer(CANOPY_RADIUS_M).intersection(study_area)
        # Учитываем только часть кроны, не перекрытую ранее рассмотренными деревьями.
        marginal=canopy if covered is None else canopy.difference(covered)
        # Добавляем вклад новой площади с тепловым весом этого дерева.
        weighted_shade+=tree.heat*marginal.area
        # Обновляем совокупную покрытую область для следующих крон.
        covered=canopy if covered is None else covered.union(canopy)
    # Снижаем базовый индекс по доле взвешенной тени и не допускаем отрицательную оценку.
    after=max(0.0,baseline-SHADE_INDEX_RESPONSE*weighted_shade/study_area.area)
    # Возвращаем исходный и сценарный показатели для сравнения.
    return baseline,after
