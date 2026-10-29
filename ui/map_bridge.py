"""Small typed bridge between Leaflet and Qt."""
# Мост преобразует вызовы из JavaScript-карты в сигналы Qt, на которые подписан Python-интерфейс.

# QObject поддерживает связь с системой сигналов Qt; Signal/Slot задают направление обмена.
# Импортируем базу QObject и инструменты декларации сигналов и JS-вызываемых слотов.
from PySide6.QtCore import QObject, Signal, Slot


# Объект-мост принимает вызовы JavaScript-карты и пересылает их остальной части Qt-приложения.
class MapBridge(QObject):
    # Сигнал сообщает координаты углов прямоугольника, который пользователь выделил на карте.
    rectangle_selected = Signal(float, float, float, float)
    # Сигнал передаёт Python номер кандидата, по которому пользователь щёлкнул.
    candidate_clicked = Signal(int)
    # Сигнал передаёт id маркера и новые GPS-координаты после его перемещения в Leaflet.
    candidate_move_requested = Signal(int, float, float)
    # Сигнал без параметров сообщает, что HTML/JavaScript-карта закончила начальную настройку.
    map_ready = Signal()

    # Объявляем JS-совместимый слот, принимающий четыре координаты прямоугольника как числа.
    @Slot(float, float, float, float)
    # Этот слот JS вызывает при завершении выделения прямоугольной области.
    def select_rectangle(self, south: float, west: float, north: float, east: float) -> None:
        # Переизлучаем событие как сигнал Qt, чтобы остальные Python-виджеты могли на него подписаться.
        self.rectangle_selected.emit(south, west, north, east)

    # Регистрируем слот без аргументов: он только сообщает о готовности страницы.
    @Slot()
    # JavaScript вызывает ready() после создания Leaflet и открытия WebChannel.
    def ready(self) -> None:
        # Сообщаем MapWidget, что отложенные команды теперь можно отправить в страницу.
        self.map_ready.emit()

    # Слот принимает целый id выбранного кандидата, который JS передаёт из маркера.
    @Slot(int)
    # JS передаёт сюда числовой id кандидата при нажатии на его маркер.
    def toggle_candidate(self, candidate_id: int) -> None:
        # Передаём id сигналом коду приложения, который обновит состояние выбранных деревьев.
        self.candidate_clicked.emit(candidate_id)

    # Слот принимает id и две GPS-координаты, полученные после перетаскивания маркера.
    @Slot(int, float, float)
    # Leaflet вызывает этот слот после перетаскивания маркера в новую точку.
    def move_candidate(self, candidate_id: int, lat: float, lon: float) -> None:
        # Сообщаем приложению id перемещаемого кандидата и новые широту/долготу.
        self.candidate_move_requested.emit(candidate_id, lat, lon)
