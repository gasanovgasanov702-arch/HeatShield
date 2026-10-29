# GeoPandas задаёт пустые слои и геометрию здания с системой координат.
import geopandas as gpd
# box строит прямоугольное здание, внутри которого проверяется запрещённая посадка.
from shapely.geometry import box

# audit_selection сверяет посадки с картой; Candidate и Placement описывают точку и выбранный план.
from core.audit import audit_selection
# Candidate — координаты предполагаемого дерева; Placement — список выбранных id и показатели размещения.
from core.free_space import Candidate
# Placement задаёт выбранные номера точек, которые независимый аудит перепроверит.
from core.optimizer import Placement


# Тест убеждается, что аудит одновременно находит посадку внутри здания и сообщает о пустых данных зелени.
def test_audit_flags_known_building_and_missing_vegetation():
    # Создаём пустые геослои в проекции UTM 43N, где координаты измеряются в метрах.
    empty=gpd.GeoDataFrame(geometry=[],crs="EPSG:32643")
    # Аудиту передаются все ожидаемые слои; пока все пусты, кроме здания, которое добавим ниже.
    layers={name:empty for name in ("buildings","roads","footways","green","water","trees","attractors")}
    # Здание занимает квадрат 10×10 м с координатами от 0 до 10 по обеим осям.
    layers["buildings"]=gpd.GeoDataFrame(geometry=[box(0,0,10,10)],crs="EPSG:32643")
    # Единственная выбранная посадка находится в центре здания (5,5), поэтому должна быть нарушением.
    result=audit_selection([Candidate(0,5,5,0,0)],Placement([0],0,0,0),layers)
    # Список нарушений не пуст: точка посадки пересекается с геометрией здания.
    assert result["violations"]
    # При пустых слоях зелени аудит должен предупредить об отсутствии данных, а не молча считать их наличными.
    assert any("нет размеченной зелени" in text.lower() for text in result["warnings"])
