# json читает сохранённый сценарий; Path строит путь к файлу независимо от текущей папки запуска.
import json
# Path нужен для поиска файла примера через расположение теста, а не текущую папку запуска.
from pathlib import Path

# GeoPandas превращает сохранённые GeoJSON-объекты в геометрические слои для аудита.
import geopandas as gpd

# Эти функции повторно проверяют сохранённое размещение, создают объекты-кандидаты и готовят систему координат.
from core.audit import audit_selection
# Candidate представляет место, сохранённое в сценарии; projected_boundary строит метрическую границу карты.
from core.free_space import Candidate
# Эта функция восстанавливает метрический контур участка из сохранённых GPS-границ.
from core.geodesy import projected_boundary
# Placement описывает размещение, Settings — его ограничения, evaluate_selection пересчитывает его показатели.
from core.optimizer import Placement, Settings, evaluate_selection


# Проверяет согласованность включённого сценария: формат, числа выбранных деревьев, геослои и метрики.
def test_shipped_real_scenario_is_consistent():
    # Находим включённый пример относительно файла теста: parents[1] — корень проекта.
    path=Path(__file__).resolve().parents[1]/"examples"/"almaty"/"almaty_center.json"
    # Открываем JSON в UTF-8 и преобразуем его текст в словарь Python `data`.
    data=json.loads(path.read_text(encoding="utf-8"))
    # Версия схемы 3 гарантирует, что тест читает формат, для которого написан.
    assert data["schema_version"]==3
    # Источник должен указывать OpenStreetMap, чтобы пример не выглядел синтетической картой.
    assert data["source"].startswith("OpenStreetMap")
    # В примере явно отмечено, что модель не обучалась статистически; это важно для честного описания результата.
    assert data["model_assumptions"]["statistically_trained"] is False
    # Преобразуем каждую запись места из JSON в объект Candidate с именованными полями.
    candidates=[Candidate(**item) for item in data["candidates"]]
    # bounds задаёт прямоугольник карты; projected_boundary возвращает его метровую геометрию и CRS.
    region,crs=projected_boundary(tuple(data["bounds"]))
    # Заново оцениваем сохранённые id жадного плана с его настройками внутри границы региона.
    placement=evaluate_selection(candidates,data["greedy"]["ids"],Settings(**data["settings"]),region)
    # В примере должно быть не меньше 100 мест, иначе он слишком мал для демонстрации выбора.
    assert len(candidates)>=100
    # Сохранённый сценарий рассчитан на 20 деревьев; сверяем число фактически выбранных id.
    assert len(placement.ids)==20
    # Аудит, записанный в JSON, не должен содержать обнаруженных нарушений размещения.
    assert data["metrics"]["audit"]["violations"]==[]
    # Пересчитанная площадь тени (м²) должна совпадать с сохранённой с точностью до 0.01 м².
    assert abs(placement.shaded_area_m2-data["greedy"]["shaded_area_m2"])<.01
    # Сюда по очереди будут собраны реальные слои карты после преобразования геометрий.
    layers={}
    # name — имя слоя (например, buildings), geo — его GeoJSON-подобное описание из сценария.
    for name,geo in data["layers"].items():
        # GeoJSON хранит объекты в списке features; если списка нет, считаем слой пустым.
        features=geo.get("features",[])
        # Непустые геометрии сначала читаем в EPSG:4326 (долгота/широта), затем переводим в CRS региона
        # для метрических проверок; пустой слой сразу создаём с целевой CRS, чтобы CRS совпадал.
        layers[name]=(gpd.GeoDataFrame.from_features(features,crs="EPSG:4326").to_crs(crs)
                      # Для пустого списка features создаём пустой слой с тем же CRS, что у проектированной области.
                      if features else gpd.GeoDataFrame(geometry=[],crs=crs))
    # Создаём Placement со всеми id кандидатов, чтобы аудит проверил каждый кандидат против слоёв карты.
    # Нули здесь — служебные показатели площади/стоимости, поскольку этому вызову важны только ids.
    audit=audit_selection(candidates,Placement([c.id for c in candidates],0,0,0),layers)
    # Проверяем, что аудит действительно просмотрел весь список мест, а не только выбранные 20.
    assert audit["checked"]==len(candidates)
    # Включённые данные не должны давать нарушений для проверенных мест.
    assert audit["violations"]==[]
    # В этом примере жадный алгоритм должен давать большую полезность, чем случайный план.
    assert data["greedy"]["utility"]>data["random"]["utility"]
