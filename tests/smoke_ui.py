"""Ручная проверка Qt WebEngine; запускайте с offscreen-переменными окружения."""
# logging нужен для ограничения шума от Qt до предупреждений и ошибок.
import logging
# Показываем только важные сообщения уровня WARNING и выше.
logging.basicConfig(level=logging.WARNING)
# QTimer остановит приложение по таймеру; QApplication и MainWindow создают настоящее окно.
from PySide6.QtCore import QTimer
# QApplication создаёт цикл событий приложения, а главное окно содержит карту WebEngine.
from PySide6.QtWidgets import QApplication
# MainWindow предоставляет карту, сигналы её готовности и JavaScript-мост для проверки drag-событий.
from ui.main_window import MainWindow
# Candidate создаёт одну тестовую точку, которую можно перетащить на карте.
from core.free_space import Candidate

# Запускаем Qt без параметров командной строки.
app = QApplication([])
# Создаём окно с картой и мостом JavaScript↔Python.
window = MainWindow()
# Инициализируем карту вокруг текущих координат, чтобы WebEngine загрузил страницу.
window._from_coordinates()
# Сюда JavaScript-обработчики запишут результаты двух проверок: перетаскивания и видимости слоёв.
checks={}

# Печатаем факт завершения загрузки карты и булево значение успеха.
window.map.loadFinished.connect(lambda ok: print("loaded",ok,flush=True))
# Показываем id кандидата и координаты, которые пришли из сигнала после его перетаскивания.
window.map.bridge.candidate_move_requested.connect(lambda candidate_id,lat,lon:print("drag signal",candidate_id,round(lat,4),round(lon,4),flush=True))
# После готовности WebEngine настраиваем слои и запускаем проверки JS-карты.
def ready():
    # Пустая GeoJSON FeatureCollection — валидный слой без геометрий.
    empty={"type": "FeatureCollection", "features": []}
    # Загружаем пустые слои зданий, дорог, зелени и воды; пустая коллекция задаёт свободный слой.
    window.map.set_layers({"buildings":empty,"roads":empty,"green":empty,"water":empty},empty)
    # Создаём одну перетаскиваемую точку в Алматы (43.238° широты, 76.888° долготы) с баллами .5.
    window.map.set_candidates([Candidate(0,0,0,43.238,76.888,.5,.5,.5)],[0])
    # Обратный вызов получает результат JavaScript-проверки и сохраняет его для assert после цикла Qt.
    def drag_state(value):
        # Записываем строку JSON, возвращённую браузерной проверкой жеста перетаскивания.
        checks["drag"]=value
        # Печатаем ответ, чтобы видеть его при ручном запуске smoke-теста.
        print("drag shows candidates",repr(value),flush=True)
    # В JavaScript начинаем перетаскивание, проверяем видимость слоя кандидатов, меняем координату на 0.0001°
    # и заканчиваем жест; возвращаются состояние drag, видимость во время перетаскивания и после него.
    window.map.page().runJavaScript("const t=afterLayer.getLayers()[0]; t.fire('dragstart'); const shown=map.hasLayer(candidateLayer); t.setLatLng([43.2381,76.8881]); t.fire('dragend'); JSON.stringify([t.dragging.enabled(),shown,map.hasLayer(candidateLayer)])",drag_state)
    # Колбэк принимает JSON-строку с видимостью каждого слоя, возвращённую браузерной страницей.
    def layer_state(state):
        # Сохраняем последовательность видимости четырёх базовых слоёв и трёх дополнительных слоёв.
        checks["layers"]=state
        # Выводим состояние слоёв для диагностики интерфейса.
        print("default layers quiet",repr(state),flush=True)
    # Читаем видимость зданий/дорог/зелени/воды, кандидатов, теплового слоя и слоя после посадки.
    window.map.page().runJavaScript("JSON.stringify(['buildings','roads','green','water'].map(k=>map.hasLayer(osmLayers[k])).concat([map.hasLayer(candidateLayer),map.hasLayer(heatLayer),map.hasLayer(afterLayer)]))",layer_state)
    # После получения двух ответов завершаем проверку через 1 секунду.
    QTimer.singleShot(1000,app.quit)
# Запускаем ready после сигнала карты, чтобы JavaScript API уже был доступен.
window.map.bridge.map_ready.connect(ready)
# Если карта не сообщит готовность, через 15 секунд всё равно завершаем окно, избегая вечного ожидания.
QTimer.singleShot(15000, app.quit)
# Запускаем Qt и ждём загрузки карты и выполнения JavaScript-проверок.
app.exec()
# Ожидается, что drag включён, кандидаты видимы во время перетаскивания и скрываются после него.
# Вторая строка состояния подтверждает начальную видимость четырёх базовых слоёв и скрытое состояние остальных.
assert checks=={"drag":"[true,true,false]","layers":"[true,false,true,true,false,false,true]"},checks
