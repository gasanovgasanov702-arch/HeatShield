# GeoPandas создаёт пустой зелёный слой с известной системой координат.
import geopandas as gpd

# Candidate задаёт место расчёта; green_deficit оценивает нехватку зелени и деревьев в окрестности.
from core.free_space import Candidate
# green_deficit оценивает нехватку озеленения; при отсутствии объектов в источнике оценка нейтральная.
from core.vegetation import green_deficit


# Проверяет важный случай: неизвестная зелень в OSM не должна автоматически означать максимальный дефицит.
def test_missing_osm_greenery_is_neutral_not_maximum_deficit():
    # Пустые геоданные в UTM 43N означают, что OSM не содержит объектов зелени/деревьев в этом примере.
    empty=gpd.GeoDataFrame(geometry=[],crs="EPSG:32643")
    # При отсутствии данных модель использует нейтральную середину шкалы 0..1 (.5),
    # а не ошибочно считает, что район доказанно совсем лишён зелени (максимальный дефицит 1).
    assert green_deficit([Candidate(0,0,0,0,0)],{"green":empty,"trees":empty})==[.5]
