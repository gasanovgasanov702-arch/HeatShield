# GeoDataFrame хранит геометрии вместе с системой координат; nx создаёт тестовый граф улиц.
import geopandas as gpd
# NetworkX создаёт минимальный граф улиц, который требуется объекту CityData.
import networkx as nx
# LineString моделирует дорогу, Point проверяет координату места, а box создаёт прямоугольные участки.
from shapely.geometry import LineString, Point, box

# find_free_space строит возможные места для посадки; CityData собирает минимальные данные города.
from core.free_space import find_free_space
# CityData объединяет границу, слои, граф улиц и систему координат для поиска мест.
from core.map_loader import CityData


# Проверяет, что сетка посадочных мест исключает здание, дорожный отступ, ориентир и воду.
def test_candidates_avoid_building_and_road():
    # EPSG:32643 задаёт плоские координаты в метрах, что позволяет проверять отступы обычной арифметикой.
    crs="EPSG:32643"
    # Квадрат от (0,0) до (120,120) м — исследуемая зона размером 120×120 м.
    boundary=box(0,0,120,120)
    # Пустой слой нужен для типов объектов, которых в этой тестовой карте нет.
    empty=gpd.GeoDataFrame(geometry=[],crs=crs)
    # Сначала все типы слоёв пусты; ниже добавляем объекты-препятствия и ориентиры.
    layers={key:empty for key in ("buildings","roads","footways","green","water","trees","attractors")}
    # Здание занимает квадрат 40..80 м; проверяем защитный отступ, расширяя прямоугольник до 35..85 м.
    layers["buildings"]=gpd.GeoDataFrame(geometry=[box(40,40,80,80)],crs=crs)
    # Дорога проходит горизонтально по y=15 м от x=0 до x=120 м.
    layers["roads"]=gpd.GeoDataFrame(geometry=[LineString([(0,15),(120,15)])],crs=crs)
    # Прямоугольный ориентир (например, людное место) нужен как дополнительная запрещённая зона.
    layers["attractors"]=gpd.GeoDataFrame(geometry=[box(0,80,30,110)],crs=crs)
    # Пруд занимает прямоугольник справа от здания; кандидаты не должны оказаться внутри воды.
    layers["water"]=gpd.GeoDataFrame(geometry=[box(90,40,115,80)],crs=crs)
    # Собираем город: границы широты/долготы здесь тестовые, улицы представлены пустым графом, проекция — в метрах.
    city=CityData((0,0,1,1),boundary,empty,nx.MultiDiGraph(),crs)
    # Просим расставить сетку кандидатов с шагом 20 м; первый элемент результата здесь не используется.
    _,candidates=find_free_space(city,layers,spacing_m=20)
    # Непустой список подтверждает, что при заданных препятствиях свободные точки всё ещё находятся.
    assert candidates
    # Ни одна точка кандидата не должна попадать в расширенный на 5 м прямоугольник вокруг здания.
    assert all(not box(35,35,85,85).contains(Point(c.x,c.y)) for c in candidates)
    # Полуширина запретной зоны дороги равна 5 м: расстояние по y от линии y=15 должно быть не меньше 5 м.
    assert all(abs(c.y-15)>=5 for c in candidates)
    # Проверяем, что кандидаты не находятся внутри прямоугольной зоны ориентира.
    assert all(not box(0,80,30,110).contains(Point(c.x,c.y)) for c in candidates)
    # Проверяем аналогичное исключение для водоёма, заданного границами x=90..115 и y=40..80 м.
    assert all(not box(90,40,115,80).contains(Point(c.x,c.y)) for c in candidates)
