# json читает обратно экспортированный сценарий, чтобы проверять содержимое файла.
import json

# Candidate задаёт посадочное место; compare и алгоритмы строят метрики для сохраняемых результатов.
from core.free_space import Candidate
# compare строит сводные метрики для двух планов; Settings и алгоритмы создают эти планы.
from core.metrics import compare
# Настройки и оба алгоритма нужны, чтобы создать проверяемый пример экспорта.
from core.optimizer import Settings, greedy, random_placement
# Эти функции записывают один сценарий сразу в JSON, GeoJSON, CSV и PNG.
from services.export import save_csv, save_geojson, save_map_png, save_scenario


# Проверяет, что разные форматы экспорта сохраняют координаты, источник, отметки выбора и корректный файл PNG.
def test_exports_keep_real_coordinates_and_provenance(tmp_path):
    # Один кандидат имеет координаты проекции (500000,4750000) м и реальные долготу 75.1°, широту 42.9°.
    # Оценки .7, .8, .9 — условные баллы тестового примера.
    candidates=[Candidate(0,500000,4750000,42.9,75.1,.7,.8,.9)]
    # Настройки разрешают одно дерево и бюджет 10 000 денежных единиц.
    settings=Settings(trees=1,budget=10000)
    # Строим жадный и воспроизводимый случайный варианты; короткие имена g и r означают два плана.
    g=greedy(candidates,settings);r=random_placement(candidates,settings)
    # Считаем показатели сравнения планов без пешеходных линий (последний аргумент — пустой список).
    metrics=compare(g,r,settings,candidates,[])
    # tmp_path — временная папка pytest; файлы теста автоматически удалятся после запуска.
    scenario=tmp_path/"case.json"
    # Сохраняем сценарий с границами участка (южная/западная/северная/восточная координаты).
    save_scenario(scenario,(42.89,75.09,42.91,75.11),candidates,settings,g,r,metrics)
    # GeoJSON должен хранить геометрию выбранных мест в стандартном порядке координат долгота, широта.
    save_geojson(tmp_path/"case.geojson",candidates,g)
    # CSV нужен для табличного просмотра кандидатов и отметки, был ли каждый выбран.
    save_csv(tmp_path/"case.csv",candidates,g)
    # PNG — изображение карты до/после; пустой словарь означает, что дополнительных слоёв в фикстуре нет.
    save_map_png(tmp_path/"case.png",(42.89,75.09,42.91,75.11),{},candidates,g.ids)
    # Читаем JSON обратно, чтобы проверить содержимое уже записанного файла, а не только вызов функции.
    data=json.loads(scenario.read_text(encoding="utf-8"))
    # Открываем GeoJSON для проверки сохранённых координат в его структуре features.
    geo=json.loads((tmp_path/"case.geojson").read_text(encoding="utf-8"))
    # В JSON должен сохраниться источник данных, указывающий OpenStreetMap.
    assert data["source"].startswith("OpenStreetMap")
    # Ограничения модели обязаны попасть в экспорт, чтобы читатель видел допущения и границы результата.
    assert data["limitations"]
    # GeoJSON хранит координаты как [долгота, широта], то есть [75.1, 42.9], а не наоборот.
    assert geo["features"][0]["geometry"]["coordinates"]==[75.1,42.9]
    # utf-8-sig снимает BOM Excel-файла; наличие заголовка selected подтверждает поле выбора.
    assert "selected" in (tmp_path/"case.csv").read_text(encoding="utf-8-sig")
    # PNG начинается фиксированной сигнатурой из 8 байтов; это проверяет, что экспорт — настоящее PNG.
    assert (tmp_path/"case.png").read_bytes().startswith(b"\x89PNG")
