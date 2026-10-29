"""Shared scenario metrics; indices are relative estimates."""
# Этот модуль собирает показатели двух планов для сравнения; все индексы относительные.

# Откладываем вычисление типов для современного синтаксиса аннотаций.
from __future__ import annotations

# LineString представляет пешеходный маршрут, Point — положение дерева.
from shapely.geometry import LineString, Point
# Объединяем отдельные геометрии, чтобы оценивать их общей сетью или общей кроной.
from shapely.ops import unary_union

# Candidate содержит идентификатор и координаты каждой возможной позиции.
from core.free_space import Candidate
# Функция рассчитывает исходный и сценарный индексы тепловой нагрузки.
from core.heat_model import scenario_area_heat_index
# Импортируем размер кроны и структуры результатов/настроек из оптимизатора.
from core.optimizer import CANOPY_RADIUS_M, Placement, Settings


# Считаем эффект выбранного плана на тепло и затенение нанесённых пеших маршрутов.
def _environment_metrics(result: Placement, candidates: list[Candidate], route_lines: list, study_area=None) -> dict:
    # Создаём быстрый поиск кандидата по его уникальному номеру.
    lookup={c.id:c for c in candidates}
    # Получаем объекты деревьев, присутствующие в результате и в исходном наборе кандидатов.
    chosen=[lookup[i] for i in result.ids if i in lookup]
    # Рассчитываем показатели тепла до плана и после него.
    before,after=scenario_area_heat_index(candidates,chosen,study_area)
    # Строим объединённую геометрию крон выбранных деревьев.
    canopy=unary_union([Point(c.x,c.y).buffer(CANOPY_RADIUS_M) for c in chosen])
    # Объединяем только корректные маршруты, заданные хотя бы двумя координатами.
    lines=unary_union([LineString(coords) for coords in route_lines if len(coords)>=2])
    # Считаем процент длины нанесённых маршрутов, пересекающий область крон.
    route_share=100*lines.intersection(canopy).length/lines.length if not lines.is_empty and lines.length>0 else 0.0
    # Вычисляем относительное снижение теплового индекса, если исходное значение положительно.
    reduction=100*(before-after)/before if before>0 else 0.0
    # Возвращаем словарь именованных показателей, пригодный для отчёта и интерфейса.
    return {"heat_index_before":before,"heat_index_after":after,"heat_reduction_percent":max(0.0,reduction),
            # Показываем, какой процент нанесённой пешеходной сети лежит под кронами.
            "mapped_walk_network_shaded_percent":route_share}


# Собираем метрики основного и случайного планов в общий словарь для отчёта.
def compare(greedy_result: Placement, random_result: Placement, settings: Settings, candidates: list[Candidate] | None = None, route_lines: list | None = None, study_area=None) -> dict:
    # Подменяем отсутствующие необязательные данные пустыми списками для единых вычислений.
    candidates=candidates or []
    # Пустой список позволяет измерителям работать, даже если маршруты не переданы.
    route_lines=route_lines or []
    # Случайный план используется как база, с которой сравнивается полезность жадного плана.
    base = random_result.utility
    # Сравнение полезности честнее, когда в планах одинаковое число деревьев.
    comparable=len(greedy_result.ids)==len(random_result.ids)
    # Вычисляем процент прироста; None означает, что база нулевая или планы несопоставимы.
    gain = ((greedy_result.utility / base) - 1) * 100 if base > 0 and comparable else None
    # Формируем подробные метрики для жадного плана: цена, площадь тени, время и окружение.
    greedy_metrics={"trees": len(greedy_result.ids), "cost": len(greedy_result.ids) * settings.cost_per_tree,
                   # Площадь тени измеряется в м², utility — сумма относительных баллов.
                   "shade_m2": greedy_result.shaded_area_m2, "relative_utility": greedy_result.utility,
                   # Время расчёта задаётся в секундах; остальные поля добавляет оценка окружения.
                   "seconds": greedy_result.elapsed_s, **_environment_metrics(greedy_result,candidates,route_lines,study_area)}
    # Собираем такой же набор показателей для случайного плана.
    random_metrics={"trees": len(random_result.ids), "cost": len(random_result.ids) * settings.cost_per_tree,
                   # Для контрольного плана сохраняем те же площадь тени и относительную полезность.
                   "shade_m2": random_result.shaded_area_m2, "relative_utility": random_result.utility,
                   # Длительность в секундах и экологические показатели нужны для честного сравнения.
                   "seconds": random_result.elapsed_s, **_environment_metrics(random_result,candidates,route_lines,study_area)}
    # Сохраняем целевой процент затенения, заданный пользователем.
    target=settings.target_shade_percent
    # Рассчитываем фактическую долю затенённой площади в процентах; при неизвестной площади это 0.
    actual=100*greedy_result.shaded_area_m2/study_area.area if study_area is not None and study_area.area>0 else 0.0
    # Добавляем фактический процент к метрикам жадного плана.
    greedy_metrics["study_area_shaded_percent"]=actual
    # Долю покрытия случайного плана тоже считаем в процентах площади участка.
    random_metrics["study_area_shaded_percent"]=(100*random_result.shaded_area_m2/study_area.area if study_area is not None and study_area.area>0 else 0.0)
    # Возвращаем единый результат, включая достижение цели и сопоставимость планов.
    # Возвращаем ключевые показатели: выбранный метод, данные двух планов и факт достижения цели.
    return {
        # Помечаем, какой алгоритм построил основной рекомендуемый план.
        "plan_method": "greedy",
        # Вложенный словарь содержит количество деревьев, цену и экологические показатели основного плана.
        "greedy": greedy_metrics,
        # Здесь лежат те же поля для контрольного случайного плана.
        "random": random_metrics,
        # Записываем требуемое покрытие, достигнутое покрытие и остаток до цели.
        "goal": {"target_percent":target,"actual_percent":actual,
                 # reached показывает выполнение цели, shortfall — недостающие процентные пункты.
                 "reached":target>0 and actual+1e-8>=target,"shortfall_percent":max(0.0,target-actual)},
        # Сопоставимость True означает, что оба варианта содержат одинаковое число деревьев.
        "comparable":comparable,
        # gain — процент выигрыша полезности жадного плана относительно случайной базы.
        "improvement_percent": gain,
    }
