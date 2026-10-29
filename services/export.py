"""Сохраняет воспроизводимый сценарий и рекомендованные координаты."""

# Отложенные аннотации позволяют описывать типы аргументов без выполнения их выражений при импорте.
from __future__ import annotations

# csv формирует таблицу, а json сохраняет вложенный сценарий и геоданные в текстовом виде.
import csv
# json сериализует словари и списки сценария в стандартный текстовый формат JSON.
import json
# asdict превращает dataclass-объекты настроек, кандидатов и планов в обычные словари.
from dataclasses import asdict
# datetime даёт время анализа; timezone гарантирует отметку UTC, не зависящую от часового пояса компьютера.
from datetime import datetime, timezone
# Path предоставляет безопасные операции с путями и файлами на разных ОС.
from pathlib import Path
# math нужен для косинуса широты при правильном соотношении масштаба карты.
import math

# Эти константы описывают принятые радиусы и веса модели; их экспорт позволяет видеть допущения сценария.
from config import (CANOPY_RADIUS_M, HEAT_BASE, HEAT_BUILDING_WEIGHT, HEAT_CONTEXT_RADIUS_M,
                    # Доля влияния зелени, дорог и деревьев сохраняется отдельно, чтобы допущения можно было проверить в JSON.
                    HEAT_GREEN_WEIGHT, HEAT_ROAD_WEIGHT, MAPPED_TREE_PROXY_RADIUS_M,
                    # Максимальная реакция индекса на тень нужна для понимания, насколько модель меняет относительную оценку.
                    SHADE_INDEX_RESPONSE)
# Candidate задаёт поля каждого возможного места; after_heat_scores пересчитывает относительную жару после посадки.
from core.free_space import Candidate
# Отдельная функция пересчитывает индекс жары для точек на экспортируемой карте «после».
from core.heat_model import after_heat_scores
# Placement содержит выбранные id и показатели плана; Settings хранит бюджет и прочие ограничения.
from core.optimizer import Placement, Settings


# Текст заранее перечисляет ограничения данных и модели; он копируется в экспорты, чтобы результаты не воспринимали как разрешение на посадку.
LIMITATIONS = "OSM and optional local GeoJSON coverage varies. Free geometry does not establish land ownership, utilities, soil suitability, exact sidewalk edges or all actual vegetation. Heat and pedestrian values are relative model estimates, not measurements. The 15% canopy response is an uncalibrated scenario assumption, not a temperature prediction."


# Собирает полный сценарий в один JSON-файл, чтобы расчёт можно было сохранить и загрузить повторно.
def save_scenario(path: Path, bounds: tuple, candidates: list[Candidate], settings: Settings, greedy: Placement, random: Placement, metrics: dict, layers: dict | None = None, free_layer: dict | None = None, route_lines: list | None = None) -> None:
    # Создаём папку назначения, включая отсутствующие родительские папки; существующую папку оставляем как есть.
    path.parent.mkdir(parents=True, exist_ok=True)
    # Формируем документ версии 3 — единый снимок входных данных, параметров, обоих планов и измеренных метрик.
    payload = {"schema_version": 3, "source": "OpenStreetMap via OSMnx; optional local GeoJSON", "analyzed_at_utc": datetime.now(timezone.utc).isoformat(),
               # Сохраняем время со смещением UTC, чтобы можно было определить, когда именно получены изменчивые данные карты.
               "model_assumptions": {"canopy_radius_m":CANOPY_RADIUS_M,"max_index_response_under_canopy":SHADE_INDEX_RESPONSE,
                                     # Радиусы имеют метры в названии; веса и базовый уровень объясняют расчёт относительного индекса, а False отмечает отсутствие калибровки/обучения.
                                     "mapped_tree_proxy_radius_m":MAPPED_TREE_PROXY_RADIUS_M,"heat_context_radius_m":HEAT_CONTEXT_RADIUS_M,
                                      # Базовый уровень и вес зданий показывают их вклад в относительную оценку жары.
                                      "heat_base":HEAT_BASE,"building_weight":HEAT_BUILDING_WEIGHT,
                                      # Эти веса описывают вклад дорог и зелёных участков, а не температуру в градусах.
                                      "road_weight":HEAT_ROAD_WEIGHT,"green_weight":HEAT_GREEN_WEIGHT,
                                      # False явно сообщает, что отклик не калибровался и статистического обучения не было.
                                      "response_calibrated":False,"statistically_trained":False},
               # Границы задают исследуемый прямоугольник; asdict превращает настройки в JSON-совместимый словарь.
               "limitations": LIMITATIONS, "bounds": bounds, "settings": asdict(settings),
               # asdict сохраняет поля каждой точки и планы; metrics содержит сводные числа, уже рассчитанные приложением.
               "candidates": [asdict(c) for c in candidates], "greedy": asdict(greedy), "random": asdict(random), "metrics": metrics,
               # Слои карты, свободные участки и маршруты включаются целиком; None заменяется пустой структурой ради стабильной схемы.
               "layers": layers or {}, "free_layer": free_layer or {}, "route_lines": route_lines or []}
    # ensure_ascii=False оставляет русский текст читаемым, indent=2 форматирует JSON для просмотра человеком.
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# Экспортирует выбранные посадочные точки в GeoJSON, который можно открыть в GIS-картах.
def save_geojson(path: Path, candidates: list[Candidate], placement: Placement) -> None:
    # Быстрый поиск кандидата по числовому id нужен ниже, чтобы план превратить в географические точки.
    lookup = {c.id: c for c in candidates}
    # FeatureCollection — стандарт GeoJSON: каждая выбранная точка получает геометрию и атрибуты для GIS-программ.
    payload = {"type": "FeatureCollection", "name": "HeatShield recommendations", "properties": {"source": "OpenStreetMap; optional local GeoJSON", "analyzed_at_utc": datetime.now(timezone.utc).isoformat(), "limitations": LIMITATIONS,
               # В общих свойствах указываются источник, UTC-время и главные модельные допущения для всего файла.
               "model_assumptions":{"canopy_radius_m":CANOPY_RADIUS_M,"max_index_response_under_canopy":SHADE_INDEX_RESPONSE}},
               # GeoJSON требует порядок координат [долгота, широта]; в свойствах остаются баллы/контекст и отметка о полевой проверке.
               "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [lookup[i].lon, lookup[i].lat]},
                             # Идентификатор и два индекса позволяют узнать место и сравнить его расчётную жару/пешеходную активность.
                             "properties": {"candidate_id": i, "heat_index": lookup[i].heat, "pedestrian_index": lookup[i].pedestrian,
                                            # Индекс дефицита зелени и контекстные расстояния дополняют свойства точки данными карты.
                                            "green_deficit_index": lookup[i].green_deficit, **lookup[i].context,
                                            # Флаг напоминает, что модельная рекомендация требует проверки участка человеком.
                                            "verification_required": True}} for i in placement.ids if i in lookup]}
    # Записываем экспорт в UTF-8 и сохраняем отступы, чтобы GeoJSON можно было открыть и читать вручную.
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# Записывает каждого кандидата отдельной строкой таблицы вместе с отметкой его выбора.
def save_csv(path: Path, candidates: list[Candidate], placement: Placement) -> None:
    # set позволяет за O(1) проверять для каждой строки, включён ли id в итоговый план.
    selected = set(placement.ids)
    # newline="" предотвращает лишние пустые строки CSV в Windows; utf-8-sig помогает Excel распознать UTF-8.
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        # В таблицу добавляются расстояния до объектов в метрах и количество нанесённых зелёных объектов.
        context_fields=["buildings_distance_m","roads_distance_m","footways_distance_m","green_distance_m",
                        # Вторая часть списка задаёт расстояния до других объектов и число зелёных объектов в контексте.
                        "trees_distance_m","water_distance_m","attractors_distance_m","mapped_green_objects"]
        # Фиксируем порядок столбцов: координаты и оценки, контекст, выбран ли кандидат, источник, дата и ограничения.
        writer = csv.DictWriter(stream, fieldnames=["id", "lat", "lon", "heat", "pedestrian", "green_deficit", *context_fields,
                                                      # Эти столбцы объясняют статус выбора, происхождение, время расчёта и необходимость проверки.
                                                      "selected", "source", "analyzed_at_utc", "limitations", "verification_required"])
        # Записываем заголовок, чтобы числа в строках имели понятные названия.
        writer.writeheader()
        # Один общий момент времени относится ко всему пакету строк; ISO-формат и UTC устраняют неоднозначность даты.
        analyzed_at=datetime.now(timezone.utc).isoformat()
        # Каждое место становится отдельной строкой таблицы, включая невыбранные варианты для сравнения.
        for c in candidates:
            # Копируем координаты/индексы/контекст кандидата и отмечаем его выбор; ограничения напоминают о необходимости проверки на месте.
            writer.writerow({"id": c.id, "lat": c.lat, "lon": c.lon, "heat": c.heat, "pedestrian": c.pedestrian,
                             # Для каждой строки сохраняем рассчитанный дефицит, признак участия в плане и источник OpenStreetMap.
                             "green_deficit": c.green_deficit, "selected": c.id in selected, "source": "OpenStreetMap; optional local GeoJSON",
                             # Один UTC-момент и общие ограничения поясняют происхождение данных; True требует полевой проверки.
                             "analyzed_at_utc": analyzed_at, "limitations": LIMITATIONS, "verification_required": True,
                             # Добавляем расстояния/счётчики из контекста кандидата; отсутствующее поле будет пустым значением.
                             **{field:c.context.get(field) for field in context_fields}})


# В эту функцию передаются путь PNG, границы участка, реальные слои, кандидаты и выбранные id.
def save_map_png(path: Path, bounds: tuple, layers: dict, candidates: list[Candidate], selected: list[int]) -> None:
    """Строит географически привязанный обзор карты напрямую, без снимка экрана."""
    # Рисуем PNG напрямую через backend Agg, поэтому не требуется открытое окно или снимок экрана.
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    # Figure и патчи/форматтеры создают сам рисунок, геометрии, шкалы и подписи осей.
    # Figure хранит холст графика, Polygon превращает контуры площадей в цветные пятна.
    from matplotlib.figure import Figure
    # MplPolygon — имя для matplotlib-полигона, чтобы не путать его с геометриями Shapely.
    from matplotlib.patches import Polygon as MplPolygon
    # Форматтер округляет подписи координат, MaxNLocator ограничивает количество делений осей.
    from matplotlib.ticker import FormatStrFormatter, MaxNLocator
    # shape переводит GeoJSON-геометрию в объект Shapely для рисования её частей.
    from shapely.geometry import shape

    # Создаём полотно 10×8 дюймов при 160 dpi; светлый фон задаётся и у полотна, и у графика.
    fig=Figure(figsize=(10,8),dpi=160,facecolor="#f7faf8")
    # Agg связывает Figure с растровым рендерером, который сохранит изображение в файл.
    FigureCanvasAgg(fig)
    # Создаём единственную ось, где будут нарисованы слои и точки.
    ax=fig.add_subplot(111)
    # Подбираем цвет фона внутри области карты.
    ax.set_facecolor("#f7faf8")
    # Цвета слоёв различают свободные места, природные объекты, здания, улицы и ориентиры.
    colors={"free":"#eaca4c","green":"#65a96d","water":"#78c5e4","buildings":"#8b9293",
            "roads":"#444c50","footways":"#b78d61","trees":"#248644","attractors":"#e18747"}
    # Рисуем сначала площади и линейные объекты, чтобы поверх них были видны точки кандидатов.
    for name in ("free","green","water","buildings","roads","footways","trees","attractors"):
        # Слой без features ничего не рисует; get(...,{}) делает отсутствие слоя безопасным.
        for feature in layers.get(name,{}).get("features",[]):
            # GeoJSON geometry может отсутствовать у некорректной/неполной записи.
            geometry=feature.get("geometry")
            # Пропускаем запись, если рисовать нечего.
            if not geometry:continue
            # Преобразуем GeoJSON в Shapely и разбиваем составные геометрии на отдельные части.
            geom=shape(geometry)
            # Составная Shapely-геометрия содержит дочерние части; простую геометрию оборачиваем в список из неё самой.
            pieces=list(geom.geoms) if hasattr(geom,"geoms") else [geom]
            # Выбираем способ отображения по типу части: полигон, линия или точка.
            for part in pieces:
                # Полигоны показывают площадь; прозрачность свободной зоны ниже, чтобы видеть карту под ней.
                if part.geom_type=="Polygon":
                    # Берём внешний контур полигона; свободные участки рисуем полупрозрачно, другие площади плотнее.
                    ax.add_patch(MplPolygon(list(part.exterior.coords),closed=True,facecolor=colors[name],edgecolor="none",alpha=.55 if name=="free" else .85))
                # Линии дорог толще пешеходных дорожек, чтобы важная сеть читалась лучше.
                elif part.geom_type=="LineString":
                    # xy — координаты линии; отрисовываем её выбранным цветом, делая дороги толще дорожек.
                    x,y=part.xy;ax.plot(x,y,color=colors[name],linewidth=2 if name=="roads" else 1,alpha=.8)
                # Точечные объекты (например, нанесённые деревья) рисуются маленькими маркерами поверх полигонов.
                elif part.geom_type=="Point":
                    # Точка получает фиксированный размер 14 пунктов и слой отображения выше полигонов.
                    ax.scatter([part.x],[part.y],s=14,color=colors[name],zorder=4)
    # Строим поиск по id и превращаем только выбранные существующие id в объекты Candidate.
    lookup={c.id:c for c in candidates}
    # Пропускаем неизвестные id, чтобы некорректная ссылка в selected не остановила построение карты.
    chosen=[lookup[i] for i in selected if i in lookup]
    # Если список не пуст, пересчитываем относительный индекс после размещения выбранных деревьев.
    if candidates:
        # Для каждого кандидата вычисляем условную жару после размещения списка chosen.
        heats=after_heat_scores(candidates,chosen)
        # Цвет каждой точки соответствует оценке 0..1; фиксированный диапазон сохраняет одинаковый смысл цветов на разных картах.
        heat_points=ax.scatter([c.lon for c in candidates],[c.lat for c in candidates],s=12,c=heats,cmap="coolwarm",vmin=0,vmax=1,alpha=.8,zorder=5)
        # Легенда справа объясняет, что цвета обозначают относительный индекс, а не измеренную температуру.
        fig.colorbar(heat_points,ax=ax,shrink=.65,label="Относительный индекс жары")
    # Выделяем новые деревья яркими крупными точками и добавляем подпись только при наличии выбора.
    if chosen:
        ax.scatter([c.lon for c in chosen],[c.lat for c in chosen],s=115,color="#1eec69",edgecolor="#164d2c",linewidth=1.2,zorder=6,label="Новые деревья")
        # Легенда поясняет, что большие яркие маркеры обозначают новые деревья.
        ax.legend(loc="upper right")
    # Распаковываем географические границы в градусах, чтобы задать охват карты.
    south,west,north,east=bounds
    # Ограничиваем оси границами участка в порядке x=долгота и y=широта.
    ax.set_xlim(west,east);ax.set_ylim(south,north)
    # Поправка косинусом средней широты компенсирует то, что градус долготы сужается к полюсам.
    ax.set_aspect(1/max(.1,math.cos(math.radians((south+north)/2))))
    # Ограничиваем число делений, чтобы координатная сетка не загромождала небольшую карту.
    ax.xaxis.set_major_locator(MaxNLocator(5));ax.yaxis.set_major_locator(MaxNLocator(6))
    # Пять знаков после запятой дают удобную точность географических координат в подписях осей.
    ax.xaxis.set_major_formatter(FormatStrFormatter("%.5f"));ax.yaxis.set_major_formatter(FormatStrFormatter("%.5f"))
    # Подписываем координатные оси на русском языке.
    ax.set_xlabel("Долгота");ax.set_ylabel("Широта")
    # Заголовок показывает состояние сценария: с выбранными посадками или исходную карту.
    ax.set_title("HeatShield — после" if chosen else "HeatShield — до",fontsize=15,weight="bold")
    # Подпись на рисунке указывает источник карты и предупреждает о предварительном характере модели.
    fig.text(.02,.01,"© OpenStreetMap contributors · Предварительная модель, нужна проверка на месте",fontsize=8,color="#41544a")
    # Сохраняем PNG с обрезкой пустых полей и метаданными источника/UTC-времени/ограничений внутри файла.
    fig.savefig(path,format="png",bbox_inches="tight",metadata={"Title":"HeatShield scenario map","Source":"OpenStreetMap",
                # Записываем UTC-время изображения и те же ограничения модели в метаданные PNG.
                "AnalyzedAtUTC":datetime.now(timezone.utc).isoformat(),"Limitations":LIMITATIONS})
