"""Conservative geometric candidates; every result requires field verification."""
# Модуль ищет точки, свободные от известных объектов на карте; это предварительный расчёт.
# Даже найденная точка требует проверки на месте, потому что карта может быть неполной.

# Эта директива позволяет использовать современные подсказки типов без раннего вычисления типов.
from __future__ import annotations

# dataclass автоматически создаёт удобный класс для хранения данных-кандидата.
from dataclasses import dataclass, field

# GeoPandas хранит геометрию вместе с системой координат.
import geopandas as gpd
# Point нужен для представления проверяемых точек на плоскости в метрах.
from shapely.geometry import Point
# unary_union объединяет множество препятствий в одну геометрию.
from shapely.ops import unary_union

# CityData содержит границу города и сведения о его координатной системе.
from core.map_loader import CityData


# Декоратор создаёт Candidate как неизменяемую запись после заполнения её полей.
@dataclass(frozen=True)
# Candidate описывает одну возможную позицию дерева; frozen запрещает случайно менять её поля.
class Candidate:
    # id — уникальный номер точки внутри списка кандидатов.
    id: int
    # x и y — координаты в проекции участка, обычно в метрах.
    x: float
    # y — вертикальная координата в той же проекции и тех же метрах, что и x.
    y: float
    # lat и lon — широта и долгота той же точки для показа на обычной карте.
    lat: float
    # lon — долгота в градусах; её порядок в GPS-паре отличается от x.
    lon: float
    # heat — относительная оценка тепловой нагрузки рядом с точкой.
    heat: float = 0.0
    # pedestrian — относительная оценка важности точки для пешеходов.
    pedestrian: float = 0.0
    # green_deficit — оценка удалённости от существующей зелени.
    green_deficit: float = 0.0
    # context хранит дополнительные числовые сведения или None; по умолчанию словарь пуст.
    context: dict[str, float | int | None] = field(default_factory=dict)


# Извлекаем корректные фигуры слоя и при необходимости расширяем их на заданные метры.
def _shapes(frame: gpd.GeoDataFrame, buffer: float = 0) -> list:
    # Берём только корректные непустые геометрии; buffer расширяет их на указанное число метров.
    return [g.buffer(buffer) if buffer else g for g in frame.geometry if g is not None and not g.is_empty and g.is_valid]


# Исключаем препятствия и размещаем сетку возможных мест внутри оставшейся территории.
def find_free_space(city: CityData, layers: dict[str, gpd.GeoDataFrame], *, spacing_m: int = 30, max_candidates: int = 1800) -> tuple[object, list[Candidate]]:
    # Собираем расширенные контуры объектов, чтобы точка не оказалась вплотную к ним.
    obstacles = []
    # Для каждого слоя задан защитный отступ в метрах; зелёные зоны считаются занятыми целиком.
    for name, distance in (("buildings", 5), ("roads", 5), ("footways", 2), ("sidewalks", 8), ("green", 0), ("water", 5), ("trees", 5), ("restricted", 5), ("attractors", 2)):
        # Новые слои необязательны для старых тестовых сценариев.
        if name in layers:
            # Добавляем геометрии с защитным отступом; тротуар у дороги получает 8 м.
            obstacles.extend(_shapes(layers[name], distance))
    # Вычитаем препятствия из городской границы; если препятствий нет, свободна вся граница.
    free = city.boundary.difference(unary_union(obstacles)) if obstacles else city.boundary
    # Оставляем достаточно крупные полигоны, пригодные для дальнейшего поиска.
    polygons = [g for g in (list(free.geoms) if hasattr(free, "geoms") else [free]) if g.geom_type == "Polygon" and g.area >= 40]
    # Если подходящих участков нет, возвращаем свободную геометрию и пустой список точек.
    if not polygons:
        # Когда нет подходящих полигонов, вернуть пустой список точек безопаснее сеточного перебора.
        return free, []
    # Объединяем все подходящие части в одну область проверки.
    valid_space = unary_union(polygons)
    # Здесь будут накапливаться точки сетки, которые попали в свободную область.
    points = []
    # Определяем прямоугольник границ, чтобы не перебирать координаты за пределами города.
    minx, miny, maxx, maxy = city.boundary.bounds
    # Генерируем регулярную сетку с шагом spacing_m по оси X.
    for x in __import__("numpy").arange(minx + spacing_m / 2, maxx, spacing_m):
        # Для каждой координаты X перебираем позиции по оси Y с тем же шагом.
        for y in __import__("numpy").arange(miny + spacing_m / 2, maxy, spacing_m):
            # Создаём геометрическую точку из координат сетки.
            p = Point(float(x), float(y))
            # Берём точку только внутри свободной зоны и минимум в двух метрах от её края.
            if valid_space.contains(p) and valid_space.boundary.distance(p) >= 2.0:
                # Сохраняем подходящую точку для последующего перевода в широту и долготу.
                points.append(p)
    # Если точек слишком много, равномерно прореживаем список до заданного лимита.
    if len(points) > max_candidates:
        # step показывает, через сколько элементов исходного списка брать следующий.
        step = len(points) / max_candidates
        # Индексы распределены по всему списку, чтобы сохранить географическое покрытие.
        points = [points[int(i * step)] for i in range(max_candidates)]
    # Пустой результат удобнее вернуть сразу, не создавая пустую GeoSeries.
    if not points:
        # При пустой сетке сохраняем границу свободной зоны, но сообщаем, что точек для посадки нет.
        return free, []
    # Указываем исходную проекцию точек и преобразуем их в стандартные GPS-координаты.
    gps = gpd.GeoSeries(points, crs=city.crs).to_crs("EPSG:4326")
    # Собираем Candidate: x/y остаются в метрах, lat/lon берутся из преобразованной серии.
    return free, [Candidate(i, p.x, p.y, gps.iloc[i].y, gps.iloc[i].x) for i, p in enumerate(points)]
