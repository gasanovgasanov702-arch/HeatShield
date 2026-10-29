"""Embedded Leaflet map."""
# Виджет показывает HTML-карту Leaflet внутри окна Qt и передаёт ей команды из Python.

# json безопасно превращает Python-значения в литералы для JavaScript-вызовов.
import json
# logging записывает ошибки и сообщения из консоли JavaScript.
import logging
# Path помогает найти HTML-карту рядом с этим файлом независимо от текущей папки запуска.
from pathlib import Path

# QUrl формирует URL, который понимает встроенный браузер Qt.
from PySide6.QtCore import QUrl
# Канал позволяет JavaScript-странице вызывать методы Python-объекта.
from PySide6.QtWebChannel import QWebChannel
# Страница перехватывает консоль JS, а настройки управляют доступом локального HTML.
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
# QWebEngineView — виджет браузера, в котором отображается Leaflet.
from PySide6.QtWebEngineWidgets import QWebEngineView

# Передаём карте общие настройки проекта: центр, масштаб, размер кроны и реакцию тени.
from config import CANOPY_RADIUS_M, DEFAULT_LAT, DEFAULT_LON, DEFAULT_ZOOM, SHADE_INDEX_RESPONSE
# MapBridge принимает события, которые страница Leaflet отправляет обратно в Python.
from ui.map_bridge import MapBridge


# Страница встроенного браузера перехватывает сообщения консоли JS-карты.
class LoggingPage(QWebEnginePage):
    # Qt вызывает этот метод при сообщении console.* из JavaScript-карты.
    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        # Указываем источник JS, его строку и текст сообщения; уровень Qt здесь не записывается.
        logging.warning("Map JavaScript %s:%s: %s", source_id, line_number, message)


# Виджет загружает Leaflet-страницу и передаёт команды между Python и браузером Qt.
class MapWidget(QWebEngineView):
    # parent — необязательный родительский виджет Qt, управляющий временем жизни этого объекта.
    def __init__(self, parent=None) -> None:
        # Инициализируем базовый браузерный виджет с тем же родителем.
        super().__init__(parent)
        # Устанавливаем страницу, которая будет записывать сообщения JavaScript в журнал Python.
        self.setPage(LoggingPage(self))
        # Флаг показывает, сообщил ли HTML-код, что карта готова принимать команды.
        self._ready = False
        # До готовности карты сохраняем JS-команды здесь, чтобы не потерять ранние обновления.
        self._pending: list[str] = []
        # Создаём Python-приёмник событий, вызываемых картой через WebChannel.
        self.bridge = MapBridge(self)
        # Когда страница сообщает о готовности, отправляем ей все накопленные команды.
        self.bridge.map_ready.connect(self._flush_pending)
        # WebChannel связывает Python-объекты с JS-контекстом конкретной страницы браузера.
        self.channel = QWebChannel(self.page())
        # Регистрируем bridge под именем, по которому его найдёт JavaScript-код страницы.
        self.channel.registerObject("bridge", self.bridge)
        # Подключаем канал к странице, чтобы JS смог получить зарегистрированный объект.
        self.page().setWebChannel(self.channel)
        # Разрешаем локальной HTML-карте загружать удалённые тайлы и ресурсы карты.
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        # Разрешаем HTML-карте читать локальные файлы, нужные её ресурсам.
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        # Открываем map.html из папки assets, расположенной рядом с модулем интерфейса.
        self.setUrl(QUrl.fromLocalFile(str(Path(__file__).parent / "assets" / "map.html")))

    # Отправляет JS-команду сразу или ставит её в очередь до готовности карты.
    def _run(self, script: str) -> None:
        # Когда JS-страница готова, сразу исполняем переданную ей команду.
        if self._ready:
            # Qt запускает переданную JavaScript-строку в контексте загруженной HTML-карты.
            self.page().runJavaScript(script)
        # До готовности страницы откладываем команду, например обновление слоя карты.
        else:
            # Очередь сохранит строку до сигнала готовности страницы от WebChannel.
            self._pending.append(script)

    # Выполняет все команды, накопленные до сигнала готовности WebChannel.
    def _flush_pending(self) -> None:
        # Фиксируем, что WebChannel уже сообщил: карта загрузилась и готова.
        self._ready = True
        # Выполняем каждую команду, которую Python накопил во время загрузки HTML.
        for script in self._pending:
            # Выполняем эту команду в браузерном контексте карты.
            self.page().runJavaScript(script)
        # Очищаем очередь, чтобы эти же команды не запустились повторно.
        self._pending.clear()

    # Центрирует карту и задаёт масштаб, соответствующий радиусу области в метрах.
    def focus_area(self, lat: float, lon: float, radius_m: int) -> None:
        # Передаём координаты в градусах и радиус в метрах как корректные JavaScript-числа.
        self._run(f"window.focusArea({json.dumps(lat)}, {json.dumps(lon)}, {json.dumps(radius_m)});")

    # Перемещает Leaflet к заданному GPS-центру города.
    def focus_city(self, lat: float, lon: float) -> None:
        # Передаём Leaflet точку центра в порядке широта, затем долгота.
        self._run(f"window.focusCity({json.dumps(lat)}, {json.dumps(lon)});")

    # Просит карту показать прямоугольник по южной, западной, северной и восточной границам.
    def focus_bounds(self, south: float, west: float, north: float, east: float) -> None:
        # Сериализуем границы в порядке юг, запад, север, восток для JS-функции карты.
        self._run(f"window.focusBounds({json.dumps([south,west,north,east])});")

    # Удаляет с Leaflet-слоя рамку, которой пользователь выбрал участок.
    def clear_selection(self) -> None:
        # Просим JS удалить визуальную рамку выбранного прямоугольника.
        self._run("window.clearSelection();")

    # Очищает на карте слои и маркеры, созданные предыдущим расчётом.
    def clear_analysis(self) -> None:
        # Просим JS убрать созданные анализом слои и маркеры кандидатов.
        self._run("window.clearAnalysis();")

    # Возвращает камеру карты к центру и масштабу, заданным конфигурацией.
    def reset_view(self) -> None:
        # Передаём центровые координаты и уровень масштаба из настроек по умолчанию.
        self._run(f"window.focusCity({DEFAULT_LAT}, {DEFAULT_LON}, {DEFAULT_ZOOM});")

    # Передаёт в JavaScript GeoJSON-слои и геометрию доступного пространства.
    def set_layers(self, layers: dict, free_layer: dict) -> None:
        # Добавляем свободную область отдельным GeoJSON-слоем и сериализуем объект для JavaScript.
        payload = json.dumps({**layers, "free": free_layer}, ensure_ascii=False)
        # JS-карта получает JSON и сама обновляет отображаемые географические слои.
        self._run(f"window.setLayers({payload});")

    # Передаёт кандидатов и выбранные id для отрисовки маркеров и их сценарного эффекта.
    def set_candidates(self, candidates: list, selected: list[int], settings=None) -> None:
        # В JSON для маркера кладём id, GPS-точку, оценки факторов и дополнительный контекст.
        payload = [{"id": c.id, "lat": c.lat, "lon": c.lon, "heat": c.heat,
                    # Передаём отдельно оценку пешеходов, дефицит зелени и поясняющий контекст маркера.
                    "pedestrian": c.pedestrian, "green_deficit": c.green_deficit,"context":c.context} for c in candidates]
        # Радиус измеряется в метрах, отклик — доля, веса задают относительную важность факторов.
        model={"canopyRadius":CANOPY_RADIUS_M,"shadeResponse":SHADE_INDEX_RESPONSE,
               # Если Settings ещё нет, все три фактора получают равные базовые веса.
               "weights":[settings.heat_weight,settings.pedestrian_weight,settings.green_weight] if settings else [1,1,1]}
        # Передаём точки, номера выбранных деревьев и параметры модели в функцию Leaflet.
        self._run(f"window.setCandidates({json.dumps(payload)}, {json.dumps(selected)}, {json.dumps(model)});")

    # Переключает на карте слой результата после посадки по сигналу чекбокса.
    def show_after(self, enabled: bool) -> None:
        # Переводим Python True/False в нижний регистр, как требует синтаксис JavaScript.
        self._run(f"window.showAfter({str(enabled).lower()});")
