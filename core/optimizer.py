"""Reproducible budgeted placement with diminishing canopy benefit."""
# Здесь строятся планы посадки, учитывающие бюджет, расстояния и пользу каждой точки.

# Откладываем вычисление аннотаций типов.
from __future__ import annotations

# math нужен для расстояний и проверки конечности чисел.
import math
# random перемешивает кандидатов для контрольного случайного плана.
import random
# time измеряет длительность работы алгоритма в секундах.
import time
# dataclass автоматически создаёт конструкторы структур настроек и результата.
from dataclasses import dataclass

# Радиус кроны задаётся в конфигурации и измеряется в метрах.
from config import CANOPY_RADIUS_M
# Candidate — одна геометрически возможная точка посадки с оценками пользы.
from core.free_space import Candidate
# Point позволяет построить круг кроны вокруг выбранного дерева.
from shapely.geometry import Point
# unary_union объединяет перекрывающиеся круги в общую площадь тени.
from shapely.ops import unary_union



# Декоратор формирует неизменяемую запись настроек, чтобы параметры не менялись во время расчёта.
@dataclass(frozen=True)
# Settings содержит параметры плана; frozen не позволяет менять их случайно во время расчёта.
class Settings:
    # Максимум деревьев, который пользователь хотел бы посадить.
    trees: int = 20
    # Общая сумма денег на программу посадки.
    budget: float = 200000.0
    # Цена одного дерева в денежных единицах бюджета.
    cost_per_tree: float = 10000.0
    # Минимально допустимое расстояние между центрами деревьев, в метрах.
    minimum_distance_m: float = 12.0
    # Веса приоритета теплового фактора, пешеходов и нехватки зелени.
    heat_weight: float = 1.0
    # Приоритет близости к пешеходам; большее значение усиливает этот фактор в балле.
    pedestrian_weight: float = 1.0
    # Приоритет нехватки зелени; большее значение сильнее поднимает точки вдали от зелени.
    green_weight: float = 1.0
    # seed фиксирует последовательность случайного перебора для повторяемого сравнения.
    seed: int = 42
    # Доля площади участка, которую желательно покрыть кронами, в процентах от 0 до 100.
    target_shade_percent: float = 0.0

    # Рассчитываем верхний лимит посадки после проверки параметров.
    def limit(self) -> int:
        # Собираем параметры, которым запрещено быть бесконечными или NaN.
        values=(self.budget,self.cost_per_tree,self.minimum_distance_m,self.heat_weight,self.pedestrian_weight,self.green_weight,self.target_shade_percent)
        # Проверяем конечность каждого числового параметра до любых сравнений и делений.
        if not all(math.isfinite(value) for value in values):
            # Невалидные числа нельзя безопасно использовать при сравнении и делении.
            # Прерываем расчёт, чтобы бесконечность или NaN не исказили лимит.
            raise ValueError("Параметры должны быть конечными числами.")
        # Проверяем базовые ограничения: число и бюджет неотрицательны, цена положительна.
        if self.trees < 0 or self.budget < 0 or self.cost_per_tree <= 0 or self.minimum_distance_m < 0:
            # Эти границы гарантируют неотрицательный план и положительную цену дерева.
            raise ValueError("Количество, бюджет, стоимость и расстояние должны быть допустимыми.")
        # Отрицательный приоритет перевернул бы смысл оценки, поэтому он запрещён.
        if min(self.heat_weight, self.pedestrian_weight, self.green_weight) < 0:
            # Вес не может быть отрицательным, иначе фактор поменял бы смысл на противоположный.
            raise ValueError("Приоритеты не могут быть отрицательными.")
        # Целевой процент площади должен лежать в диапазоне от 0 до 100 процентов.
        if not 0 <= self.target_shade_percent <= 100:
            # Площадь участка нельзя покрыть менее чем на 0% или более чем на 100%.
            raise ValueError("Цель должна быть от 0 до 100%.")
        # Возвращаем меньшее из желаемого количества и количества, оплачиваемого бюджетом.
        return min(self.trees, int(self.budget // self.cost_per_tree))


# Декоратор автоматически создаёт конструктор для чисел и идентификаторов результата.
@dataclass
# Placement хранит итог выбранного алгоритмом плана.
class Placement:
    # ids — номера точек-кандидатов, выбранных для посадки.
    ids: list[int]
    # utility — суммарная относительная полезность выбранных деревьев.
    utility: float
    # shaded_area_m2 — площадь тени в квадратных метрах с учётом перекрытия крон.
    shaded_area_m2: float
    # elapsed_s — длительность вычисления в секундах.
    elapsed_s: float


# Объединяем три нормированных фактора в один взвешенный приоритет кандидата.
def _score(c: Candidate, settings: Settings) -> float:
    # Складываем веса факторов, чтобы получить знаменатель для среднего взвешенного балла.
    total = settings.heat_weight + settings.pedestrian_weight + settings.green_weight
    # Если все приоритеты выключены, любой кандидат получает нулевую полезность.
    if total == 0:
        # Если веса все равны нулю, результат нулевой и деление не выполняется.
        return 0.0
    # Умножаем каждую оценку кандидата на её вес и нормируем на сумму весов.
    return (settings.heat_weight * c.heat + settings.pedestrian_weight * c.pedestrian + settings.green_weight * c.green_deficit) / total


# Считаем метрическое расстояние между двумя кандидатами по их x и y.
def _distance(a: Candidate, b: Candidate) -> float:
    # Координаты x/y даны в метрах, поэтому гипотенуза даёт прямое расстояние в метрах.
    return math.hypot(a.x - b.x, a.y - b.y)


# Уменьшаем вклад дерева, если его будущая крона перекроется с уже посаженными.
def _marginal(c: Candidate, chosen: list[Candidate], settings: Settings) -> float:
    # Сначала новая крона считается полностью полезной, пока не найдено перекрытие.
    overlap = 1.0
    # Проверяем близость кандидата ко всем деревьям, которые уже вошли в план.
    for existing in chosen:
        # Расстояние между центрами точек измеряется в метрах.
        distance = _distance(c, existing)
        # Две кроны могут пересекаться, если центры ближе суммы их радиусов.
        if distance < 2 * CANOPY_RADIUS_M:
            # Уменьшаем дополнительную пользу пропорционально доле расстояния до суммы радиусов.
            overlap *= max(0.0, distance / (2 * CANOPY_RADIUS_M))
    # Возвращаем взвешенную оценку кандидата с учётом уже покрытой кронами площади.
    return _score(c, settings) * overlap


# Проверяем, можно ли добавить кандидата без нарушения минимального промежутка.
def _valid(c: Candidate, chosen: list[Candidate], settings: Settings) -> bool:
    # Новая точка подходит, если она не ближе минимального расстояния к каждому уже выбранному дереву.
    return all(_distance(c, existing) >= settings.minimum_distance_m for existing in chosen)


# Превращаем список выбранных мест в объект с итоговыми показателями плана.
def _summarize(chosen: list[Candidate], settings: Settings, elapsed: float, study_area=None) -> Placement:
    # Оба способа выбора используют одинаковый расчёт полезности и площади крон.
    # Суммируем предельную пользу каждого дерева относительно уже добавленных до него деревьев.
    utility = sum(_marginal(c, chosen[:i], settings) for i, c in enumerate(chosen))
    # Строим круги-кроны одинакового радиуса вокруг всех выбранных позиций.
    circles = [Point(c.x, c.y).buffer(CANOPY_RADIUS_M) for c in chosen]
    # Объединяем круги, чтобы перекрытия не считались дважды; при пустом плане геометрии нет.
    canopy = unary_union(circles) if circles else None
    # Считаем затенённую площадь внутри участка, если его граница известна.
    area = canopy.intersection(study_area).area if canopy is not None and study_area is not None else (canopy.area if canopy is not None else 0.0)
    # Возвращаем идентификаторы точек и рассчитанные сводные показатели.
    return Placement([c.id for c in chosen], utility, area, elapsed)


# Жадный алгоритм на каждом шаге выбирает допустимую точку с наибольшей добавочной пользой.
def greedy(candidates: list[Candidate], settings: Settings, study_area=None) -> Placement:
    # Запоминаем время старта, чтобы измерить длительность построения плана.
    start = time.perf_counter()
    # Для остановки по проценту тени обязательно нужна геометрия площади участка.
    if settings.target_shade_percent>0 and study_area is None:
        # Без площади участка процент покрытия нельзя вычислить.
        raise ValueError("Для процентной цели нужна геометрия участка.")
    # remaining хранит ещё не выбранные точки, chosen — формируемый план.
    remaining = list(candidates)
    # Пустой список будет пополняться выбранными точками по мере работы алгоритма.
    chosen: list[Candidate] = []
    # covered будет хранить область уже учтённой тени для проверки цели.
    covered=None
    # На каждом шаге добавляем не больше числа деревьев, доступного по бюджету и настройкам.
    for _ in range(settings.limit()):
        # Оставляем только точки, достаточно удалённые от всех уже выбранных деревьев.
        eligible = [c for c in remaining if _valid(c, chosen, settings)]
        # Если допустимых вариантов больше нет, план готов даже до достижения лимита.
        if not eligible:
            # Нет разрешённых точек, поэтому ограничение расстояний остановило построение плана.
            break
        # Выбираем наибольшую предельную пользу; при равенстве выигрывает меньший номер точки.
        best = max(eligible, key=lambda c: (_marginal(c, chosen, settings), -c.id))
        # Добавляем лучшую точку в план и убираем из списка будущих вариантов.
        chosen.append(best)
        # Убираем выбранное место из очереди, чтобы случайно не выбрать его повторно.
        remaining.remove(best)
        # При заданной цели обновляем площадь тени и проверяем процент покрытия участка.
        if settings.target_shade_percent>0:
            # Буфер вокруг нового места моделирует круг кроны радиусом в метрах.
            circle=Point(best.x,best.y).buffer(CANOPY_RADIUS_M)
            # Добавляем этот круг к ранее покрытой области, чтобы перекрытия не удваивали площадь.
            covered=circle if covered is None else covered.union(circle)
            # Проверяем, достигнута ли цель по отношению к общей площади study_area.
            if 100*covered.intersection(study_area).area/study_area.area+1e-9>=settings.target_shade_percent:
                # Целевой процент достигнут, дальнейшие посадки не нужны для условия остановки.
                break
    # Возвращаем общую сводку и длительность работы алгоритма в секундах.
    return _summarize(chosen, settings, time.perf_counter() - start,study_area)


# Создаём базовый план, перебирая кандидатов в воспроизводимом случайном порядке.
def random_placement(candidates: list[Candidate], settings: Settings, study_area=None) -> Placement:
    # Измеряем длительность контрольного случайного алгоритма.
    start = time.perf_counter()
    # Делаем копию, чтобы исходный список кандидатов остался в прежнем порядке.
    remaining = list(candidates)
    # Локальный генератор с фиксированным seed делает случайный контроль воспроизводимым.
    random.Random(settings.seed).shuffle(remaining)
    # Здесь будут позиции, которые случайный алгоритм сможет добавить в план.
    # В выбранном списке накапливаются точки случайного плана.
    # Здесь копятся кандидаты, принятые случайным планом.
    chosen: list[Candidate] = []
    # Перебираем точки в перемешанном порядке.
    for c in remaining:
        # Останавливаемся, когда использован весь доступный лимит деревьев.
        if len(chosen) >= settings.limit():
            # Лимит из настроек и доступного бюджета уже использован.
            break
        # Добавляем точку лишь при соблюдении минимального расстояния до выбранных.
        if _valid(c, chosen, settings):
            # Сохраняем точку только после проверки дистанции до всех выбранных.
            chosen.append(c)
    # Оцениваем случайный план той же функцией, что и жадный.
    return _summarize(chosen, settings, time.perf_counter() - start,study_area)


# Проверяем готовый список номеров и рассчитываем те же метрики, что и для алгоритмов.
def evaluate_selection(candidates: list[Candidate], ids: list[int], settings: Settings, study_area=None) -> Placement:
    # Создаём соответствие идентификатора кандидату для быстрого поиска.
    lookup = {c.id: c for c in candidates}
    # Запрещаем повторы, превышение количества/бюджета и номера, которых нет среди кандидатов.
    if len(ids) != len(set(ids)) or len(ids) > settings.limit() or any(i not in lookup for i in ids):
        # Отклоняем дубликаты, неизвестные id и список длиннее разрешённого лимита.
        raise ValueError("Выбор нарушает ограничение количества или бюджета.")
    # Преобразуем номера в объекты кандидатов в том порядке, который передал пользователь.
    chosen = [lookup[i] for i in ids]
    # Проверяем расстояние каждого дерева до тех, что стоят перед ним в переданном списке.
    if any(not _valid(c, chosen[:i], settings) for i, c in enumerate(chosen)):
        # Такой план нарушил бы требуемый промежуток между стволами.
        raise ValueError("Деревья расположены слишком близко друг к другу.")
    # Возвращаем проверенную сводку; 0.0 показывает, что время поиска здесь не измерялось.
    return _summarize(chosen, settings, 0.0,study_area)


# Заменяем одно выбранное место ближайшим проверенным кандидатом и валидируем новый план.
def move_tree(candidates: list[Candidate], selected_ids: list[int], old_id: int,
              # lat/lon — исходные координаты переноса в градусах, snap_distance_m — допуск привязки в метрах.
              lat: float, lon: float, settings: Settings, *, snap_distance_m: float = 20.0,
              # study_area ограничивает итоговую площадь крон границей участка.
              study_area=None) -> tuple[Placement, int, float]:
    # Перенос привязывается к ближайшей заранее проверенной точке и затем проверяет план целиком.
    """Move one tree to the closest verified candidate, then recheck all constraints."""
    # Перемещаемый номер обязан присутствовать в действующем плане.
    if old_id not in selected_ids:
        # Номер old_id должен ссылаться на дерево, которое уже отображается как выбранное.
        raise ValueError("Перемещаемое дерево не входит в текущий план.")
    # Требуем хотя бы одного кандидата и координаты GPS в допустимом диапазоне градусов.
    if not candidates or not (math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180):
        # Перенос невозможен без кандидатов или с GPS-координатами вне диапазона градусов.
        raise ValueError("Некорректная точка переноса.")
    # Geod рассчитывает расстояния по модели земного эллипсоида.
    from pyproj import Geod
    # Инициализируем модель WGS84, стандартную для GPS широты и долготы.
    geod=Geod(ellps="WGS84")
    # Находим кандидата с минимальным расстоянием от переданной координаты.
    nearest=min(candidates,key=lambda c:geod.inv(lon,lat,c.lon,c.lat)[2])
    # Вычисляем это расстояние в метрах для последующей проверки радиуса привязки.
    distance=geod.inv(lon,lat,nearest.lon,nearest.lat)[2]
    # Отклоняем перенос, если ближайшая заранее проверенная точка дальше допустимых метров.
    if distance>snap_distance_m:
        # Требуем, чтобы ближайший разрешённый кандидат был не дальше snap_distance_m метров.
        raise ValueError(f"Рядом нет проверенного геометрией кандидата (ближайший {distance:.0f} м). Перенесите дерево ближе к жёлтой точке.")
    # Меняем только id перемещаемого дерева, сохраняя остальные выбранные точки.
    new_ids=[nearest.id if candidate_id==old_id else candidate_id for candidate_id in selected_ids]
    # Проверяем весь обновлённый план и возвращаем результат, новый id и расстояние привязки.
    return evaluate_selection(candidates,new_ids,settings,study_area),nearest.id,distance
