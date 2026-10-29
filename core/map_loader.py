# Модуль загружает объекты OpenStreetMap и пешеходную сеть для выбранной области.
"""Download real OpenStreetMap objects with OSMnx."""

# Аннотации типов не нужно вычислять сразу при импорте модуля.
from __future__ import annotations

# dataclass автоматически создаёт удобный контейнер для нескольких результатов загрузки.
from dataclasses import dataclass
# os читает переменные окружения, например стандартную папку локального кэша Windows.
import os
# Path помогает безопасно составлять пути к кэшу независимо от разделителей ОС.
from pathlib import Path
# sys позволяет отличить обычный запуск от собранного приложения.
import sys

# GeoPandas хранит OSM-объекты в таблице с геометриями.
import geopandas as gpd
# NetworkX представляет улицы и тропы как узлы и рёбра графа.
import networkx as nx
# OSMnx загружает объекты и дорожные графы через API OpenStreetMap.
import osmnx as ox
# box импортирован для прямоугольной геометрии области.
from shapely.geometry import box

# URL сервиса Overpass берётся из общей конфигурации приложения.
from config import OVERPASS_URL
# Эта функция создаёт проекцию области, где единицы координат — метры.
from core.geodesy import projected_boundary


# Перечисляем OSM-теги, которые нужны для зданий, улиц, зелени и мест притяжения.
TAGS = {
    # True означает запрос объектов с любым значением этого тега.
    "building": True, "highway": True, "leisure": ["park", "garden", "playground", "pitch"],
    # Для landuse загружаем только указанные виды зелёного землепользования.
    "landuse": ["grass", "forest", "recreation_ground", "meadow", "orchard", "construction"],
    # Природные объекты ограничены деревьями, лесом, водой и кустарником.
    "natural": ["tree", "tree_row", "tree_group", "wood", "water", "scrub"], "waterway": True,
    # Дорога с тегом tree_lined тоже указывает на существующий ряд деревьев.
    "tree_lined": True,
    # Для мест притяжения берём важные общественные учреждения и рынки.
    "amenity": ["school", "kindergarten", "university", "hospital", "marketplace", "parking"],
    # Железнодорожные пути не должны попадать в кандидаты на посадку.
    "railway": True,
    # Также учитываются магазины и объекты общественного транспорта.
    "shop": True, "public_transport": True,
}


# Контейнер объединяет границы, объектную карту, граф прогулок и систему координат.
@dataclass
# Эта структура передаёт между функциями данные о территории и дорожной сети.
class CityData:
    # bounds хранит географические границы в градусах: юг, запад, север, восток.
    bounds: tuple[float, float, float, float]  # south, west, north, east
    # boundary — контур участка в проекции, где x и y измеряются в метрах.
    boundary: object  # projected shapely Polygon
    # features — GeoDataFrame с объектами OSM и их геометриями.
    features: gpd.GeoDataFrame
    # walk_graph — ориентированный мультиграф улиц и троп, где рёбра могут иметь длину в метрах.
    walk_graph: nx.MultiDiGraph
    # crs описывает систему координат таблицы и графа после преобразования.
    crs: object


# Загружаем данные для прямоугольника bounds и возвращаем их в едином метрическом CRS.
def load_city(bounds: tuple[float, float, float, float]) -> CityData:
    # Распаковываем четыре границы; порядок здесь широта юг/север и долгота запад/восток.
    south, west, north, east = bounds
    # Проверяем географические диапазоны и убеждаемся, что юг/запад меньше севера/востока.
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        # Порядок границ должен описывать непустой прямоугольник внутри диапазонов Земли.
        raise ValueError("Некорректные границы территории.")
    # Разрешаем кэш OSMnx, чтобы повторный запрос той же области мог использовать сохранённый ответ.
    ox.settings.use_cache = True
    # В собранном приложении кэш лежит в профиле пользователя, в режиме разработки — внутри проекта.
    cache_root = (Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "HeatShield" / "cache"
                  # Сборка приложения использует профиль пользователя, разработка — папку проекта.
                  if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1] / "data" / "cache")
    # Создаём папку кэша и все отсутствующие родительские папки.
    cache_root.mkdir(parents=True, exist_ok=True)
    # Сообщаем OSMnx, где хранить ответы сервера.
    ox.settings.cache_folder = str(cache_root)
    # Настраиваем сервер Overpass, через который OSMnx получает объекты карты.
    ox.settings.overpass_url = OVERPASS_URL
    # Отключаем внутреннюю паузу OSMnx между запросами; общий лимит учитывается конфигурацией сервера.
    ox.settings.overpass_rate_limit = False
    # Устанавливаем максимальное ожидание ответа API в 60 секунд.
    ox.settings.requests_timeout = 60
    # Указываем серверу название приложения и учебное назначение запросов.
    ox.settings.http_user_agent = "HeatShield/1.0 (educational urban heat planning)"
    # Для OSMnx 2.x bbox передаётся как запад, юг, восток, север в градусах.
    bbox = (west, south, east, north)  # OSMnx 2.x order
    # Загружаем геометрические объекты, подходящие хотя бы под один из тегов TAGS.
    try:
        # Загружаем все геометрические объекты bbox, которые совпали с тегами TAGS.
        features = ox.features_from_bbox(bbox, TAGS)
    # Если сервер вернул пустой ответ, создаём пустую геотаблицу в исходной системе широты/долготы.
    except ox._errors.InsufficientResponseError:
        # Пустой ответ Overpass представляем пустой таблицей в системе широты и долготы.
        features = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    # Загружаем граф именно для ходьбы; retain_all сохраняет отдельные несвязанные компоненты сети.
    graph = ox.graph_from_bbox(bbox, network_type="walk", retain_all=True)
    # Получаем метрическую геометрию границы и выбранную для неё систему координат.
    boundary,crs=projected_boundary(bounds)
    # Перепроецируем объекты OSM в ту же систему, чтобы расстояния вычислялись в метрах.
    features = features.to_crs(crs)
    # Перепроецируем узлы и рёбра уличного графа в ту же систему, что и объекты.
    graph = ox.project_graph(graph, to_crs=crs)
    # Возвращаем все подготовленные данные в одном объекте CityData.
    return CityData(bounds, boundary, features, graph, crs)
