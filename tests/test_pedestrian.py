# GeoPandas собирает точки ориентиров в геослой, NetworkX строит искусственную пешеходную сеть.
import geopandas as gpd
# NetworkX создаёт небольшой граф маршрутов, у которого тесту известен ожидаемый результат.
import networkx as nx
# Point создаёт узлы интереса, box — прямоугольную область, в которой проверяем оценку доступности.
from shapely.geometry import Point, box

# Candidate — тестовое место посадки; CityData объединяет геометрию города и пешеходный граф.
from core.free_space import Candidate
# CityData передаёт сеть и область расчёту; pedestrian_scores возвращает нормированную оценку для каждого места.
from core.map_loader import CityData
# Проверяемая функция выдаёт оценку востребованности места на этом графе.
from core.pedestrian import pedestrian_scores


# Проверяет расчёт на проецированном графе из одного 100-метрового ребра без внешнего SciPy.
def test_projected_walk_graph_needs_no_scipy():
    # Проекция EPSG:32643 задаёт метры, чтобы 100 единиц длины ребра означали 100 м.
    crs="EPSG:32643"
    # MultiDiGraph допускает направленные улицы и несколько рёбер между двумя узлами.
    graph=nx.MultiDiGraph()
    # Указываем CRS в метаданных графа: pedestrian_scores использует это для понимания координат узлов.
    graph.graph["crs"]=crs
    # Узел 1 находится в начале координат (0 м,0 м).
    graph.add_node(1,x=0.0,y=0.0)
    # Узел 2 расположен в 100 м к востоку от первого.
    graph.add_node(2,x=100.0,y=0.0)
    # Соединяем узлы ребром длиной 100 м; так создаётся минимальная пешеходная сеть.
    graph.add_edge(1,2,length=100.0)
    # Два ориентира (attractors) совпадают с концами маршрута и используют ту же метрическую CRS.
    attractions=gpd.GeoDataFrame(geometry=[Point(0,0),Point(100,0)],crs=crs)
    # Граница от -10 до 110 м охватывает оба узла; широта/долгота в заглушке не участвуют в расчёте.
    city=CityData((0,0,1,1),box(-10,-10,110,10),attractions,graph,crs)
    # Считаем пешеходную оценку одного кандидата (50 м,5 м) по графу и двум ориентирам.
    scores=pedestrian_scores(city,{"attractors":attractions},[Candidate(0,50,5,0,0)])
    # На один кандидат должна вернуться ровно одна оценка.
    assert len(scores)==1
    # Оценка нормирована: строго больше нуля и не превышает верхнюю границу 1.
    assert 0<scores[0]<=1
