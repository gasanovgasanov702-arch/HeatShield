# Этот модуль оценивает относительную близость кандидатов к местам притяжения и пешеходным маршрутам.
"""Conditional demand proxy using OSM attractors and walk-network geometry."""

# Аннотации типов остаются подсказками и не влияют на вычисления.
from __future__ import annotations

# NetworkX находит кратчайшие маршруты по графу улиц и троп.
import networkx as nx
# LineString строит линию для ребра без явной геометрии, Point — точку кандидата.
from shapely.geometry import LineString, Point
# Объединяет наборы точек или линий в одну геометрию для поиска расстояния.
from shapely.ops import unary_union

# Candidate содержит номер и координаты потенциального места посадки.
from core.free_space import Candidate
# CityData предоставляет граф пешеходной сети, загруженный для выбранного района.
from core.map_loader import CityData


# Считаем для каждого кандидата показатель близости к OSM-местам притяжения и сетевым маршрутам.
def pedestrian_scores(city: CityData, layers: dict, candidates: list[Candidate]) -> list[float]:
    # Для площадных объектов берём внутреннюю представительную точку; пустые и отсутствующие геометрии пропускаем.
    attractions = [g.representative_point() for g in layers["attractors"].geometry if g is not None and not g.is_empty]
    # Если кандидатов нет, возвращаем пустой список, чтобы длины результатов совпадали.
    if not candidates:
        # Пустому набору входных точек соответствует пустой набор результатов.
        return []
    # Без мест притяжения спрос оценить нечем, поэтому каждому кандидату ставим ноль.
    if not attractions:
        # При отсутствии мест притяжения всем кандидатам назначается нейтральный ноль.
        return [0.0] * len(candidates)
    # Берём дорожный граф: вершины — точки улиц, рёбра — участки путей.
    graph = city.walk_graph
    # Если в графе не хватает координат или данные некорректны, ниже будет запасной расчёт от точек притяжения.
    try:
        # OSMnx's projected nearest_nodes needs optional SciPy. Small bounded areas
        # can use a direct metric search without another heavyweight dependency.
        # Создаём список (номер узла, x, y); в проецированной системе x и y заданы в метрах.
        node_positions=[(node,float(data["x"]),float(data["y"])) for node,data in graph.nodes(data=True)]
        # Для первых 80 мест притяжения находим ближайший узел по квадрату евклидова расстояния в метрах.
        nodes=[min(node_positions,key=lambda item:(item[1]-p.x)**2+(item[2]-p.y)**2)[0]
               # Ограничение 80 уменьшает объём поиска маршрутов для больших наборов объектов.
               for p in attractions[:80]]
        # Здесь накапливаются геометрии найденных отрезков пешеходных маршрутов.
        paths = []
        # Соединяем места попарно: первый с вторым, третий с четвёртым и так далее.
        for origin, target in zip(nodes[::2], nodes[1::2]):
            # Каждый маршрут ищем отдельно, потому что между некоторыми парами граф может быть разорван.
            try:
                # Находим самый короткий путь по весу length, то есть по длине рёбер в метрах.
                route = nx.shortest_path(graph, origin, target, weight="length")
                # Разбираем список узлов маршрута на соседние пары рёбер.
                for u,v in zip(route,route[1:]):
                    # У параллельных рёбер между узлами получаем все варианты атрибутов.
                    edge_data=graph.get_edge_data(u,v)
                    # Выбираем вариант с наименьшей длиной; если длина не задана, считаем её бесконечной.
                    edge=min(edge_data.values(),key=lambda item:item.get("length",float("inf")))
                    # Сохраняем готовую геометрию ребра, если она есть в исходных OSM-данных.
                    geom=edge.get("geometry")
                    # Если геометрии нет, строим прямой отрезок между координатами конечных узлов.
                    if geom is None:
                        # Улица без собственной линии представляется отрезком между координатами узлов.
                        geom=LineString([(graph.nodes[u]["x"],graph.nodes[u]["y"]),
                                         # Конечный узел задаёт вторую пару метрических координат этого сегмента.
                                         (graph.nodes[v]["x"],graph.nodes[v]["y"])])
                    # Добавляем ребро маршрута в общий набор линий.
                    paths.append(geom)
            # Пара узлов без соединения пропускается, остальные пары продолжают обрабатываться.
            except nx.NetworkXNoPath:
                # Несвязанные компоненты графа не дают маршрут для этой пары мест.
                continue
        # Объединяем найденные линии; если маршрутов не получилось, используем точки мест притяжения.
        route_geometry = unary_union(paths) if paths else unary_union(attractions)
    # При ошибке данных графа расстояния будут считаться только от мест притяжения.
    except (ValueError, KeyError):
        # При неполных данных графа строим запасную геометрию из мест притяжения.
        route_geometry = unary_union(attractions)
    # Объединяем все места притяжения для одного измерения расстояния до ближайшего из них.
    attraction_geometry = unary_union(attractions)
    # В этом списке будет по одному числу от 0 до 1 для каждого кандидата.
    scores = []
    # Рассчитываем отдельный показатель для каждой точки посадки.
    for c in candidates:
        # Координаты x и y кандидата уже находятся в проекции и измеряются в метрах.
        p = Point(c.x, c.y)
        # Близость к притяжению линейно падает до нуля на расстоянии 250 метров.
        near_attraction = max(0.0, 1.0 - p.distance(attraction_geometry) / 250.0)
        # Близость к маршруту линейно падает до нуля на расстоянии 80 метров.
        near_route = max(0.0, 1.0 - p.distance(route_geometry) / 80.0)
        # Усредняем два показателя поровну: половина веса за места, половина — за близость к маршруту.
        scores.append(0.5 * near_attraction + 0.5 * near_route)
    # Возвращаем результаты в том же порядке, что и входные кандидаты.
    return scores
