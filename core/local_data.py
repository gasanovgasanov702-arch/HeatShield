# Этот модуль добавляет местную инвентаризацию деревьев и запретных мест к данным OSM.
"""Read user supplied WGS84 GeoJSON as additional planning constraints."""

# Аннотации типов можно читать без преждевременного импорта всех зависимостей.
from __future__ import annotations

# json читает стандартный формат GeoJSON с координатами долгота, широта.
import json
# Path позволяет проверять размер файла перед его открытием.
from pathlib import Path

# GeoPandas хранит геометрии вместе с системой координат.
import geopandas as gpd
# shape превращает GeoJSON-геометрию в объект для пространственных расчётов.
from shapely.geometry import shape

# CityData содержит метрическую проекцию выбранного участка.
from core.map_loader import CityData


# Читаем только валидные геометрии выбранного типа из небольшого локального файла.
def read_local_geojson(filename: str, city: CityData, *, trees: bool) -> gpd.GeoDataFrame:
    # Допускаем только GeoJSON: другие форматы могут требовать неизвестную систему координат.
    path = Path(filename)
    # Ограничение размера защищает интерфейс от случайной загрузки огромного файла.
    if path.suffix.lower() not in (".geojson", ".json") or path.stat().st_size > 20_000_000:
        raise ValueError("Нужен файл GeoJSON не больше 20 МБ.")
    # По стандарту GeoJSON координаты географические в WGS84.
    data = json.loads(path.read_text(encoding="utf-8"))
    # Принимаем обычную коллекцию объектов и одиночный объект Feature.
    if data.get("type") == "FeatureCollection":
        features = data.get("features", [])
    # Одиночный Feature удобно экспортировать из простых ГИС-инструментов.
    elif data.get("type") == "Feature":
        features = [data]
    # Произвольный JSON не должен молча превращаться в пустую карту.
    else:
        raise ValueError("Файл должен содержать GeoJSON FeatureCollection или Feature.")
    # Неправдоподобно большой список объектов здесь не нужен для одного небольшого участка.
    if len(features) > 100_000:
        raise ValueError("Слишком много объектов GeoJSON для одного участка.")
    # Собираем подходящие геометрии, чтобы потом единым действием сменить проекцию.
    geometries = []
    # Обходим каждый объект файла и проверяем его геометрию.
    for feature in features:
        # Пустой объект пропускается, поскольку он ничего не запрещает.
        if not feature or not feature.get("geometry"):
            continue
        # Неверную геометрию нельзя безопасно применять как препятствие.
        geometry = shape(feature["geometry"])
        # Для инвентаризации нужны точки деревьев или линии рядов деревьев.
        allowed = ("Point", "MultiPoint", "LineString", "MultiLineString") if trees else ("Polygon", "MultiPolygon")
        # Несоответствующий тип означает вероятную ошибку выбора файла.
        if geometry.geom_type not in allowed or geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"GeoJSON содержит неподходящую или повреждённую геометрию: {geometry.geom_type}.")
        # Сохраняем геометрию для последующего пересчёта в метры.
        geometries.append(geometry)
    # Пустой набор не должен создавать ложное впечатление, что местные данные учтены.
    if not geometries:
        raise ValueError("В GeoJSON нет подходящих объектов.")
    # Координаты файла переводим в метрическую проекцию конкретного города.
    frame = gpd.GeoDataFrame(geometry=geometries, crs="EPSG:4326").to_crs(city.crs)
    # Оставляем только объекты, которые могут влиять на выбранный участок.
    # Отсутствие объектов в выбранном районе — возможная ошибка координат файла.
    inside = frame.loc[frame.intersects(city.boundary)].copy()
    # Явное сообщение не даёт принять пустой импорт за проверенную местную карту.
    if inside.empty:
        raise ValueError("В GeoJSON нет объектов внутри выбранного участка. Проверьте координаты и границы.")
    # Возвращаем только объекты, действительно относящиеся к анализу.
    return inside


# Добавляем местные геометрии к стандартным тематическим слоям.
def merge_local_layers(layers: dict[str, gpd.GeoDataFrame], city: CityData,
                       tree_file: str = "", restricted_file: str = "") -> dict[str, gpd.GeoDataFrame]:
    # Копия словаря не меняет исходную классификацию OSM у вызывающего кода.
    merged = dict(layers)
    # Инвентаризация деревьев влияет на тень, дефицит зелени и запрет посадки рядом.
    for filename, name, tree_mode in ((tree_file, "trees", True), (restricted_file, "restricted", False)):
        # Без выбранного файла исходный слой остаётся как есть.
        if not filename:
            continue
        # Неподходящий файл сообщает ошибку до расчёта кандидатов.
        extra = read_local_geojson(filename, city, trees=tree_mode)
        # Объединяем геометрии даже если всё импортированное лежит вне участка.
        merged[name] = gpd.GeoDataFrame(geometry=list(merged[name].geometry) + list(extra.geometry), crs=city.crs)
    # Возвращаем слои, которыми одинаково пользуются оптимизатор, аудит и карта.
    return merged
