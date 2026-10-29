"""Metric study boundary reconstructed consistently from geographic bounds."""
# Этот модуль переводит прямоугольную границу из градусов широты/долготы в метры.

# GeoPandas умеет назначать системе координат геометрию и преобразовывать её.
import geopandas as gpd
# box создаёт прямоугольник по крайним координатам.
from shapely.geometry import box


# Возвращаем границу территории и её локальную проекцию для расчётов в метрах.
def projected_boundary(bounds:tuple[float,float,float,float]):
    # Распаковываем границы в порядке юг, запад, север, восток; все значения пока в градусах.
    south,west,north,east=bounds
    # Строим прямоугольник: Shapely ожидает сначала долготу (запад), затем широту (юг).
    geographic=gpd.GeoSeries([box(west,south,east,north)],crs="EPSG:4326")
    # Выбираем подходящую местную UTM-проекцию, где расстояния можно считать в метрах.
    crs=geographic.estimate_utm_crs()
    # Если подходящую проекцию выбрать не удалось, дальнейшие расчёты в метрах ненадёжны.
    if crs is None:
        # Сообщаем вызывающему коду понятную ошибку вместо неправильной геометрии.
        raise ValueError("Для участка не найдена метрическая проекция.")
    # Возвращаем преобразованную геометрию границы и выбранную систему координат.
    return geographic.to_crs(crs).iloc[0],crs
