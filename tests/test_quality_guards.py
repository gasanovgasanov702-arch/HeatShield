"""Небольшие регрессионные проверки, которые защищают продукт от тихих опасных ошибок."""

# GeoPandas нужен для минимальных пустых слоёв, которые принимает геометрический аудит.
import geopandas as gpd
# pytest проверяет, что плохой шаг сетки не приводит к зависанию.
import pytest
# Shapely задаёт простой метрический квадрат участка.
from shapely.geometry import box

# audit_selection проверяет совместимость с неполными старыми сценариями.
from core.audit import audit_selection
# find_free_space строит сетку и должен сразу отклонить нулевой шаг.
from core.free_space import find_free_space
# CityData — минимальный контейнер территории для изолированной проверки.
from core.map_loader import CityData
# Placement нужен аудиту даже для пустого списка выбранных мест.
# NetworkX создаёт пустой граф, потому что тест проверяет только геометрию.
import networkx as nx
# Placement нужен аудиту даже для пустого списка выбранных мест.
from core.optimizer import Placement


# Возвращает маленький город без OSM-объектов, чтобы тест не зависел от сети.
def _city():
    # Все координаты фикстуры заданы в метрах в условной проекции.
    crs = "EPSG:32643"
    # Граница 100×100 м даёт корректную площадь для поиска сетки.
    empty = gpd.GeoDataFrame(geometry=[], crs=crs)
    # Граф прогулок здесь не нужен, но CityData требует его по контракту.
    return CityData((0, 0, 1, 1), box(0, 0, 100, 100), empty, nx.MultiDiGraph(), crs)


# Нулевой шаг должен быть ошибкой, а не бесконечным циклом numpy.arange.
def test_free_space_rejects_non_positive_grid_parameters():
    # Вызов с нулевым шагом должен остановиться сразу понятным ValueError.
    with pytest.raises(ValueError, match="положительными"):
        # Пустые слои достаточно передать словарём: до сетки проверяется сам параметр.
        find_free_space(_city(), {}, spacing_m=0)


# Старый сохранённый сценарий может не иметь новых слоёв зелени/притяжения.
def test_audit_accepts_legacy_layer_dictionary():
    # Пустой список кандидатов означает, что геометрических нарушений быть не может.
    result = audit_selection([], Placement([], 0, 0, 0), {})
    # Аудит должен вернуть предупреждения о неизвестных данных, но не упасть с KeyError.
    assert result["violations"] == []
    # Проверяем, что предупреждение действительно объясняет неполноту исходной карты.
    assert result["warnings"]
