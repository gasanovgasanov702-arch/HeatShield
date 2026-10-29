# Здесь собран общий путь обработки данных, которым пользуются интерфейс и тесты.
"""One reproducible analysis pipeline shared by UI and tests."""

# Эта директива включает отложенную обработку аннотаций типов.
from __future__ import annotations

# dataclass задаёт контейнер результата, replace копирует его с обновлёнными полями.
from dataclasses import dataclass, replace

# Point представляет кандидата при измерении расстояния до объектов.
from shapely.geometry import Point
# unary_union объединяет объекты слоя для одного измерения расстояния.
from shapely.ops import unary_union

# classify делит OSM-объекты на слои, map_layers переводит их в формат карты.
from core.city_builder import classify, map_layers
# audit_selection проверяет соблюдение отступов от объектов карты.
from core.audit import audit_selection
# Candidate — точка посадки, find_free_space находит свободную область и кандидатов.
from core.free_space import Candidate, find_free_space
# projected_boundary переводит границы в проекцию, где координаты измеряются в метрах.
from core.geodesy import projected_boundary
# heat_scores оценивает относительную жару у кандидатов.
from core.heat_model import heat_scores
# load_city загружает геометрию OSM и граф пешеходных путей.
from core.map_loader import load_city
from core.local_data import merge_local_layers
# compare вычисляет показатели сравнения планов посадки.
from core.metrics import compare
# Placement хранит план, Settings — параметры, алгоритмы строят основной и случайный планы.
from core.optimizer import Placement, Settings, greedy, random_placement
# pedestrian_scores оценивает близость к объектам и пешеходным маршрутам.
from core.pedestrian import pedestrian_scores
# green_deficit оценивает нехватку зелени около каждой точки.
from core.vegetation import green_deficit


# Декоратор создаёт стандартные методы контейнера результата.
@dataclass
# Analysis объединяет промежуточные и итоговые данные одного запуска.
class Analysis:
    # Исходные границы хранятся в градусах: юг, запад, север, восток.
    bounds: tuple[float, float, float, float]
    # layers содержит объекты карты в GeoJSON-подобном формате.
    layers: dict[str, object]
    # free_layer — допустимая геометрия посадки для показа на карте.
    free_layer: object
    # candidates содержит точки и рассчитанные для них показатели.
    candidates: list[Candidate]
    # settings хранит применённые параметры.
    settings: Settings
    # greedy хранит результат приоритетного подбора.
    greedy: Placement
    # random хранит контрольный случайный план.
    random: Placement
    # metrics содержит сравнение результатов и аудит.
    metrics: dict
    # route_lines хранит координаты линий пешеходного графа для карты.
    route_lines: list
    # Пара путей позволяет отличить результат от анализа с другими входными файлами.
    source_files: tuple[str, str] = ("", "")


# Переводим геометрию рёбер графа в список координат для карты.
def _walk_lines(graph) -> list:
    # Сюда складываем по одной линии на каждое ребро.
    result=[]
    # Граф сообщает начало, конец и атрибуты каждого уличного ребра.
    for start,end,data in graph.edges(data=True):
        # У ребра может быть подробная линия с изгибами из OSM.
        geom=data.get("geometry")
        # Выбираем подробную геометрию ребра, если OSM сохранил её.
        if geom is not None:
            # Переводим точки ломаной в обычные числовые пары для отображения.
            result.append([[float(x),float(y)] for x,y in geom.coords])
        # Если подробной линии нет, используем прямое соединение концов ребра.
        else:
            # Читаем координаты двух узлов, которые ограничивают ребро.
            a,b=graph.nodes[start],graph.nodes[end]
            # Сохраняем прямой сегмент между узлами в виде координат x,y для слоя карты.
            result.append([[float(a["x"]),float(a["y"])],[float(b["x"]),float(b["y"])]])
    # Возвращаем все линии сети, собранные из геометрий или пар узлов.
    return result


# Считаем поясняющие расстояния от каждой точки до объектов на карте.
def _candidate_context(candidates: list[Candidate], layers: dict) -> list[dict]:
    # Названия слоёв определяют, до каких объектов измеряем расстояние.
    names=("buildings","roads","footways","sidewalks","green","trees","water","restricted","attractors")
    # Ранние сценарии сохранялись до появления новых слоёв.
    names=tuple(name for name in names if name in layers)
    # Объединяем геометрии каждого слоя, пропуская пустые фигуры.
    unions={name:unary_union([g for g in layers[name].geometry if g is not None and not g.is_empty]) for name in names}
    # Здесь будет словарь расстояний для каждой точки-кандидата.
    result=[]
    # Контекст добавляется в том же порядке, что и кандидаты.
    for candidate in candidates:
        # x и y кандидата заданы в проекции в метрах.
        point=Point(candidate.x,candidate.y)
        # Получаем кратчайшее расстояние в метрах; пустому слою соответствует None.
        context={name+"_distance_m":None if unions[name].is_empty else round(point.distance(unions[name]),1) for name in names}
        # Суммируем число зон зелени и отдельных деревьев на карте.
        context["mapped_green_objects"]=len(layers["green"])+len(layers["trees"])
        # Сохраняем контекст именно для текущего кандидата.
        result.append(context)
    # Отдаём список контекстов вызывающей функции.
    return result


# Запускаем полный анализ района с заданными границами и параметрами.
def analyze(bounds: tuple[float, float, float, float], settings: Settings, local_tree_file: str = "", local_restricted_file: str = "") -> Analysis:
    # Загружаем исходные OSM-объекты, граф прогулок и метрический контур.
    city = load_city(bounds)
    # Делим загруженные объекты на тематические слои.
    layers = classify(city)
    # Местные GeoJSON дополняют OSM до построения возможных точек.
    layers = merge_local_layers(layers, city, local_tree_file, local_restricted_file)
    # Находим незанятую геометрию и возможные точки посадки.
    free, candidates = find_free_space(city, layers)
    # Рассчитываем относительный тепловой индекс для каждой точки.
    heats = heat_scores(candidates, layers)
    # Рассчитываем близость к местам притяжения и маршрутам пешего графа.
    pedestrians = pedestrian_scores(city, layers, candidates)
    # Оцениваем нехватку зелени рядом с каждой точкой.
    deficits = green_deficit(candidates, layers)
    # Измеряем расстояния до объектов карты для будущих пояснений.
    contexts = _candidate_context(candidates,layers)
    # Копируем точки с новыми значениями; индекс связывает каждую метрику с правильным кандидатом.
    candidates = [replace(c, heat=heats[i], pedestrian=pedestrians[i], green_deficit=deficits[i],context=contexts[i]) for i, c in enumerate(candidates)]
    # Проверяем всю геометрию кандидатов до выбора итоговых мест.
    audit=audit_selection(candidates,Placement([c.id for c in candidates],0.0,0.0,0.0),layers)
    # Если найдены недопустимые точки, прерываем расчёт и показываем первые три проблемы.
    if audit["violations"]:
        # Прерываем анализ, если хотя бы одна сгенерированная точка нарушает правила отступов.
        raise ValueError("Проверка кандидатов по OSM обнаружила недопустимую точку: "+"; ".join(audit["violations"][:3]))
    # Строим основной план посадки в пределах метрической границы района.
    greedy_result = greedy(candidates, settings, city.boundary)
    # Строим контрольный случайный план с таким же числом деревьев, но без цели по тени.
    random_result = random_placement(candidates, replace(settings, trees=len(greedy_result.ids), target_shade_percent=0.0),city.boundary)
    # Готовим координаты пешеходных рёбер для карты.
    route_lines=_walk_lines(city.walk_graph)
    # Записываем число точек, выбранных главным алгоритмом и проверенных аудитом.
    audit["selected_checked"]=len(greedy_result.ids)
    # Подключаем GeoPandas для преобразования свободной области в слой карты.
    import geopandas as gpd
    # json преобразует GeoJSON-текст в словарь Python.
    import json
    # Создаём геотаблицу из свободной области и указываем её метрическую систему координат.
    free_frame = gpd.GeoDataFrame(geometry=[free], crs=city.crs)
    # Переводим геометрию в градусы широты и долготы для карты и разбираем GeoJSON.
    free_layer = json.loads(free_frame.to_crs("EPSG:4326").to_json())
    # Сравниваем планы посадки с учётом кандидатов, пеших линий и границы участка.
    metrics=compare(greedy_result, random_result, settings,candidates,route_lines,city.boundary)
    # Сохраняем проверку геометрии внутри общего словаря метрик.
    metrics["audit"]=audit
    # Возвращаем полный объект, который UI может показать или экспортировать.
    return Analysis(bounds, map_layers(layers), free_layer, candidates, settings, greedy_result, random_result,
                    # Передаём отдельно рассчитанные метрики и координаты пеших линий для последующего показа.
                    metrics,route_lines,(local_tree_file,local_restricted_file))


# Повторяем подбор мест с новыми параметрами, не загружая карту заново.
def rerun(analysis: Analysis, settings: Settings) -> Analysis:
    # Восстанавливаем метрическую геометрию участка из сохранённых границ в градусах.
    study_area,_=projected_boundary(analysis.bounds)
    # Подбираем новый основной план по уже рассчитанным кандидатам.
    greedy_result = greedy(analysis.candidates, settings,study_area)
    # Пересчитываем случайный план с тем же количеством выбранных деревьев.
    random_result = random_placement(analysis.candidates, replace(settings, trees=len(greedy_result.ids), target_shade_percent=0.0),study_area)
    # Обновляем сравнение двух планов на прежних кандидатах и пешеходных линиях.
    metrics=compare(greedy_result, random_result, settings,analysis.candidates,analysis.route_lines,study_area)
    # Используем прежний аудит: координаты кандидатов и препятствий не менялись.
    metrics["audit"]=analysis.metrics.get("audit",{})
    # Если аудит существует, обновляем число точек, выбранных новым планом.
    if metrics["audit"]:metrics["audit"]={**metrics["audit"],"selected_checked":len(greedy_result.ids)}
    # Возвращаем копию результата с новыми настройками, планами и метриками.
    return replace(analysis, settings=settings, greedy=greedy_result, random=random_result,metrics=metrics)
