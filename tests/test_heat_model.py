# GeoPandas хранит тестовые участки зелени и деревья вместе с их метрической CRS.
import geopandas as gpd
# Point задаёт дерево, box — прямоугольник тестовой зелёной зоны.
from shapely.geometry import Point, box

# Candidate задаёт место, где оцениваем условный индекс жары; heat_scores возвращает число от 0 до 1.
from core.free_space import Candidate
# heat_scores вычисляет условный индекс, который сравнивают три сценария ниже.
from core.heat_model import heat_scores
# compare собирает показатели плана, а Settings/evaluate_selection создают корректный тестовый план.
from core.metrics import compare
# Settings и evaluate_selection создают допустимый план для проверки метрик пешеходной сети.
from core.optimizer import Settings, evaluate_selection


# Сравнивает один и тот же пункт без зелёного полигона и внутри него: наличие зелени должно понизить индекс.
def test_green_cover_lowers_relative_heat_index():
    # EPSG:32643 — система координат, в которой x/y измеряются в метрах; геометрии должны иметь тот же CRS.
    crs="EPSG:32643"
    # Пустые здания, дороги и зелень означают, что на карте нет известных охлаждающих/нагревающих объектов.
    empty=gpd.GeoDataFrame(geometry=[],crs=crs)
    # Проверяем точку в (50 м, 50 м); нули — её географические координаты в этой искусственной фикстуре.
    candidate=Candidate(0,50,50,0,0)
    # Получаем исходный относительный индекс жары без зелёных насаждений.
    baseline=heat_scores([candidate],{"buildings":empty,"roads":empty,"green":empty})[0]
    # Создаём участок зелени 100×100 м, целиком покрывающий точку кандидата.
    green=gpd.GeoDataFrame(geometry=[box(0,0,100,100)],crs=crs)
    # Пересчитываем тот же индекс с зелёным участком; прочие слои остаются пустыми.
    cooled=heat_scores([candidate],{"buildings":empty,"roads":empty,"green":green})[0]
    # Индекс остаётся в диапазоне 0..1 и становится строго меньше, чем без зелени.
    assert 0<=cooled<baseline<=1


# Проверяет направление изменения прокси-индекса от нанесённого дерева без заявления о градусах температуры.
def test_mapped_tree_reduces_local_heat_proxy_without_invented_temperature():
    # Все координаты теста заданы в проекции с метрами, чтобы дерево и кандидат совпали точно.
    crs="EPSG:32643"
    # Сначала задаём пустые слои, чтобы измерить базовое значение без известного дерева.
    empty=gpd.GeoDataFrame(geometry=[],crs=crs)
    # Единственный кандидат находится в точке x=50 м, y=50 м.
    candidate=Candidate(0,50,50,0,0)
    # Модель получает пустые слои зданий, дорог, зелени и деревьев.
    layers={"buildings":empty,"roads":empty,"green":empty,"trees":empty}
    # Сохраняем индекс до добавления дерева для сравнения с изменённым сценарием.
    baseline=heat_scores([candidate],layers)[0]
    # Добавляем нанесённое на карту дерево точно в точку кандидата; это не выдуманное измерение температуры.
    layers["trees"]=gpd.GeoDataFrame(geometry=[Point(50,50)],crs=crs)
    # Проверяем только направление изменения прокси-индекса: близкое дерево должно снизить оценку жары.
    assert heat_scores([candidate],layers)[0]<baseline


# Убеждается, что метрики используют тень дерева и для пешеходного покрытия, и для сравнения жары.
def test_mapped_walkway_coverage_uses_same_metric():
    # Один кандидат с оценками 0.8 создаёт простейший пример с одной выбранной посадкой.
    candidates=[Candidate(0,0,0,0,0,.8,.8,.8)]
    # План предусматривает одно дерево и бюджет 10 000 денежных единиц.
    settings=Settings(trees=1,budget=10000)
    # Исследуемая область 40×40 м; границы заданы метрами, площадь равна 1600 м².
    region=box(-20,-20,20,20)
    # Строим план, в котором выбрано единственное место с id=0.
    placement=evaluate_selection(candidates,[0],settings,region)
    # Передаём одну пешеходную линию длиной 20 м от x=-10 до x=10; сравнение получает один и тот же план
    # как жадный и случайный, чтобы измерить его покрытие и индекс до/после озеленения.
    result=compare(placement,placement,settings,candidates,[[[-10,0],[10,0]]],region)
    # Часть пешеходной сети должна попасть под расчётную тень, поэтому процент покрытия больше нуля.
    assert result["greedy"]["mapped_walk_network_shaded_percent"]>0
    # После добавления дерева прокси-индекс жары должен быть ниже исходного.
    assert result["greedy"]["heat_index_after"]<result["greedy"]["heat_index_before"]
