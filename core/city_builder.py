# Этот модуль распределяет загруженные объекты OpenStreetMap по тематическим слоям карты.
"""Classify OSM objects for map layers and analysis."""

# Аннотации типов Python обрабатываются в отложенном режиме и не меняют вычисления.
from __future__ import annotations

# GeoPandas хранит объекты карты в таблицах с колонкой геометрии.
import geopandas as gpd

# CityData — результат загрузки территории, из которого здесь берутся объекты OSM.
from core.map_loader import CityData


# Раскладываем объекты города по категориям и возвращаем таблицу геометрий для каждого слоя.
def classify(city: CityData) -> dict[str, gpd.GeoDataFrame]:
    # В features находятся загруженные объекты, их теги и геометрии в проекции территории.
    frame = city.features
    # Если объектов нет, создаём пустую копию таблицы для каждого ожидаемого слоя.
    if frame.empty:
        # Имена слоёв согласованы с тем, как их используют карта и аналитические расчёты.
        return {key: frame.copy() for key in ("buildings", "roads", "footways", "sidewalks", "green", "water", "trees", "restricted", "attractors")}
    # Вложенная функция безопасно читает текстовый тег из таблицы.
    def text_column(name: str) -> gpd.GeoSeries:
        # Если колонка есть, пустые значения заменяются пустой строкой, а значения приводятся к тексту.
        return frame[name].fillna("").astype(str) if name in frame else frame.geometry.apply(lambda _: "")
    # Для разных классов объектов читаем главные теги OSM в отдельные серии.
    highway = text_column("highway")
    # Тег natural описывает природные объекты, например воду, деревья и лес.
    natural = text_column("natural")
    # Тег leisure содержит места отдыха, например парк или игровую площадку.
    leisure = text_column("leisure")
    # Тег landuse описывает назначение участка, например газон или лес.
    landuse = text_column("landuse")
    # Велодорожки тоже занимают место, поэтому исключаем их как дороги.
    roads = highway.ne("") & ~highway.isin(["footway", "path", "pedestrian", "steps"])
    # Пешеходные маршруты включают тропы, лестницы и улицы с режимом shared space.
    footways = highway.isin(["footway", "path", "pedestrian", "steps", "living_street"])
    # Тротуар бывает записан тегом дороги без отдельной линии на карте.
    sidewalks = roads & (text_column("sidewalk").isin(["yes", "both", "left", "right"]) |
                         text_column("sidewalk:both").isin(["yes", "designated"]) |
                         text_column("sidewalk:left").isin(["yes", "designated"]) |
                         text_column("sidewalk:right").isin(["yes", "designated"]))
    # Для каждой категории строим булеву маску: True означает, что строка относится к слою.
    masks = {
        # Любое непустое значение building помечает объект как здание.
        "buildings": text_column("building").ne(""),
        # Маска дорог уже учитывает исключение пешеходных типов выше.
        "roads": roads,
        # Эта маска выделяет пешеходную инфраструктуру по разрешённым значениям highway.
        "footways": footways,
        # Геометрия здесь остаётся осью дороги: защитный отступ применяется позже.
        "sidewalks": sidewalks,
        # Зелень собирается из парков, садов, газонов, лесов, лугов и природных зарослей.
        "green": leisure.isin(["park", "garden", "playground"]) | landuse.isin(["grass", "forest", "recreation_ground", "meadow", "orchard"]) | natural.isin(["wood", "scrub", "tree_group"]),
        # Водой считаются природный водоём или любой объект, помеченный как водоток.
        "water": natural.eq("water") | text_column("waterway").ne(""),
        # Слой включает одиночные деревья и целые ряды деревьев.
        "trees": natural.isin(["tree", "tree_row", "tree_group"]) | text_column("tree_lined").isin(["yes", "both", "left", "right"]),
        # На стройке, парковке и железной дороге посадку автоматически не предлагаем.
        "restricted": landuse.eq("construction") | leisure.eq("pitch") | text_column("amenity").eq("parking") | text_column("railway").ne(""),
        # Места притяжения — объекты с тегами удобств, магазинов, транспорта или остановки автобуса.
        "attractors": text_column("amenity").ne("") | text_column("shop").ne("") | text_column("public_transport").ne("") | highway.eq("bus_stop"),
    }
    # Для каждого слоя оставляем только подходящие строки и геометрию; copy создаёт независимую таблицу.
    return {name: frame.loc[mask, ["geometry"]].copy() for name, mask in masks.items()}


# Переводим геометрии всех слоёв в GeoJSON для передачи карте.
def map_layers(layers: dict[str, gpd.GeoDataFrame]) -> dict[str, object]:
    # GeoJSON использует широту и долготу, поэтому преобразуем CRS в EPSG:4326 и сериализуем таблицу.
    return {name: __import__("json").loads(frame.to_crs("EPSG:4326").to_json()) for name, frame in layers.items()}
