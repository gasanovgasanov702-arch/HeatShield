# Эти проверки моделируют карту, где размечены тротуар, ряд деревьев и местный запрет посадки.
import json
# Временный файл нужен для проверки настоящего чтения GeoJSON с диска.
from pathlib import Path

# GeoPandas переводит тестовые объекты между градусами и метрами.
import geopandas as gpd
# NetworkX даёт пустую пешеходную сеть для небольшой искусственной карты.
import networkx as nx
# Геометрии изображают пешеходный коридор, дерево и запрещённый участок.
from shapely.geometry import LineString, Point, box, mapping

# Аудит проверяет итоговые точки независимо от генератора кандидатов.
from core.audit import audit_selection
# classify разбирает смысл OSM-тегов, а find_free_space ищет безопасную сетку.
from core.city_builder import classify
# Отдельная функция строит кандидатов только на свободной геометрии.
from core.free_space import find_free_space
# read_local_geojson и merge_local_layers подключают местную инвентаризацию.
from core.local_data import merge_local_layers, read_local_geojson
# CityData связывает объекты с метрической проекцией участка.
from core.map_loader import CityData
# Placement перечисляет выбранные id для независимой проверки.
from core.optimizer import Placement


# Создаём небольшую тестовую карту 120 на 120 метров.
def _city(features=None):
    # Одна метрическая система координат используется для всех геометрических отступов.
    crs = "EPSG:32643"
    # Пустая таблица нужна, если тест проверяет только местные GeoJSON-файлы.
    frame = features if features is not None else gpd.GeoDataFrame(geometry=[], crs=crs)
    # Граф дорог здесь пуст, потому что тест касается геометрии запретов.
    return CityData((0, 0, 1, 1), box(0, 0, 120, 120), frame, nx.MultiDiGraph(), crs)


# Проверяем, что OSM-теги создают нужные слои препятствий.
def test_osm_sidewalk_tree_row_cycleway_and_parking():
    # Четыре объекта различаются по тегам, но находятся в одной метрической системе.
    features = gpd.GeoDataFrame({
        # Первый объект — обычная дорога с тротуаром, последний — велодорожка.
        "highway": ["residential", "", "", "cycleway"],
        # Тротуар указан на дороге без собственной геометрии.
        "sidewalk": ["both", "", "", ""],
        # Второй объект описывает целый ряд уже существующих деревьев.
        "natural": ["", "tree_row", "", ""],
        # Третий объект — парковка, где автоматическая посадка запрещена.
        "amenity": ["", "", "parking", ""],
        # Геометрия линии и полигона влияет на защитные расстояния.
        "geometry": [LineString([(0, 30), (120, 30)]), LineString([(60, 0), (60, 120)]), box(80, 80, 110, 110), LineString([(0, 90), (120, 90)])],
    }, crs="EPSG:32643")
    # Классификация превращает теги в слои, которыми пользуются карта и расчёт.
    layers = classify(_city(features))
    # Проверяем каждый смысловой случай отдельно, включая ранее пропущенную велодорожку.
    assert len(layers["sidewalks"]) == 1
    assert len(layers["trees"]) == 1
    assert len(layers["restricted"]) == 1
    assert len(layers["roads"]) == 2
    # Строим плановую сетку, чтобы проверить действие слоёв в реальном геометрическом расчёте.
    _, candidates = find_free_space(_city(features), layers, spacing_m=10)
    # Рядом с осью дороги с тротуаром кандидатов нет ближе восьми метров.
    assert candidates and all(abs(c.y - 30) >= 8 for c in candidates)
    # Ряд деревьев, велодорожка и парковка тоже остаются свободными от новых точек.
    assert all(abs(c.x - 60) >= 5 and abs(c.y - 90) >= 5 and Point(c.x, c.y).distance(box(80, 80, 110, 110)) >= 5 for c in candidates)
    # Независимый аудит подтверждает отсутствие геометрических нарушений у всех кандидатов.
    audit = audit_selection(candidates, Placement([c.id for c in candidates], 0, 0, 0), layers)
    # Пустой список означает, что генератор и проверяющий согласны на этом случае.
    assert audit["violations"] == []


# Проверяем, что местная инвентаризация действительно меняет карту кандидатов.
def test_local_geojson_excludes_known_tree_and_forbidden_area(tmp_path: Path):
    # Создаём город без OSM-объектов: влияние новых файлов будет видно прямо.
    city = _city()
    # Центр и полигон переводим из метров в стандартные для GeoJSON широту и долготу.
    shapes = gpd.GeoSeries([Point(25, 25), box(70, 70, 110, 110)], crs=city.crs).to_crs("EPSG:4326")
    # Два файла намеренно разделяют существующие деревья и запретные зоны.
    tree_path, restriction_path = tmp_path / "trees.geojson", tmp_path / "no_plant.geojson"
    # Реальная сериализация проверяет контракт с внешним GeoJSON, а не готовый GeoDataFrame.
    for path, geometry in ((tree_path, shapes.iloc[0]), (restriction_path, shapes.iloc[1])):
        # GeoJSON FeatureCollection является форматом, который приложение разрешает импортировать.
        path.write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": mapping(geometry)}]}), encoding="utf-8")
    # В начале ни одна площадь не исключена.
    base = classify(city)
    # После импорта дерево и полигон добавляются в те же слои, что OSM-объекты.
    layers = merge_local_layers(base, city, str(tree_path), str(restriction_path))
    # Проверяем, что файлы действительно прочитаны и находятся внутри участка.
    assert len(layers["trees"]) == 1 and len(layers["restricted"]) == 1
    # Сетка с шагом 10 м содержит точки около заданных геометрий, если запретов нет.
    _, before = find_free_space(city, base, spacing_m=10)
    # Импорт должен уменьшить число предложенных мест.
    _, after = find_free_space(city, layers, spacing_m=10)
    # Наличие разницы подтверждает практический эффект внешних данных.
    assert len(after) < len(before)
    # Новая сетка отступает от существующего дерева минимум на пять метров.
    assert all(Point(c.x, c.y).distance(Point(25, 25)) >= 5 for c in after)
    # Ни одно предложение не попадает внутрь запретной зоны или рядом с её краем.
    assert all(Point(c.x, c.y).distance(box(70, 70, 110, 110)) >= 5 for c in after)
    # Аудит также перепроверяет все новые точки по импортированным геометриям.
    assert audit_selection(after, Placement([c.id for c in after], 0, 0, 0), layers)["violations"] == []


# Проверяем явный отказ при выборе полигона вместо списка отдельных деревьев.
def test_tree_inventory_rejects_polygon(tmp_path: Path):
    # Стандартный GeoJSON геометрически корректен, но тип не соответствует инвентаризации деревьев.
    path = tmp_path / "wrong.geojson"
    # Пишем Feature с полигоном в файл для проверки ошибки входных данных.
    path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": mapping(box(0, 0, 1, 1))}), encoding="utf-8")
    # Ошибка объясняет, почему файл не принят вместо молчаливого игнорирования.
    import pytest
    # Запускаем обычный пользовательский путь чтения файла.
    with pytest.raises(ValueError, match="неподходящую"):
        # Проверяем именно режим инвентаризации деревьев.
        read_local_geojson(str(path), _city(), trees=True)
