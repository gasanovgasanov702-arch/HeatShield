"""Main desktop workflow for real OSM analysis."""
# Главное окно связывает выбор участка, загрузку данных, оптимизацию, карту и экспорт.
# Обработчики кнопок/сигналов запускают действия и обновляют связанные виджеты.
# Откладываем вычисление типов, чтобы подсказки могли ссылаться на классы ниже по файлу.
from __future__ import annotations

# json читает и записывает сохранённые сценарии и формирует данные обмена.
import json
# math нужен для оценки площади в км² и поправки долготы по широте.
import math
# replace создаёт копию структуры с изменёнными полями, сохраняя остальные значения.
from dataclasses import replace
# Path собирает пути к файлам сценария и экспорта.
from pathlib import Path
# urlencode кодирует поисковую фразу в URL запроса к OpenStreetMap Nominatim.
from urllib.parse import urlencode
# Request/urlopen отправляют сетевой поиск места и получают HTTP-ответ.
from urllib.request import Request, urlopen

# QSignalBlocker временно глушит обратные сигналы виджета; QThreadPool запускает фоновые задачи.
# QTimer объединяет быстрые изменения цели в один пересчёт после короткой паузы.
from PySide6.QtCore import QSignalBlocker, QThreadPool, QTimer
# Импортируем стандартные Qt-виджеты, из которых строятся поля, кнопки, вкладки и компоновки.
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    # Эти компоненты нужны для групп, горизонтальной компоновки, подписей и строк ввода.
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    # Здесь перечислены прокрутка, вкладки, вертикальная компоновка и базовый виджет.
    QScrollArea, QTabWidget, QVBoxLayout, QWidget)

# Название приложения и максимальный размер области берутся из единой конфигурации.
from config import APP_NAME, MAX_AREA_KM2
# Candidate восстанавливает точки посадки при открытии файла сценария.
from core.free_space import Candidate
# projected_boundary переводит GPS-границы в метры для расчёта площадей и расстояний.
from core.geodesy import projected_boundary
# Парсер читает ссылки Google Maps, а валидатор проверяет широту и долготу.
from core.google_parser import parse_google_maps_url, resolve_short_google_url, validate_coordinates
# compare собирает метрики для показываемого плана и контрольного случайного плана.
from core.metrics import compare
# Импортируем модели плана, проверку ручного выбора и привязку перетаскивания к кандидату.
from core.optimizer import Placement, Settings, evaluate_selection, move_tree
# Analysis хранит результат конвейера; analyze запускает новый разбор, rerun пересчитывает план.
from core.pipeline import Analysis, analyze, rerun
# Worker позволяет выполнять сетевой и географический расчёт вне главного UI-потока.
from services.background_worker import Worker
# Функции экспорта записывают сценарий, таблицы и картинки карты.
from services.export import save_csv, save_geojson, save_map_png, save_scenario
# Составные панели отвечают за настройки, аудит, цель, карту и показатели.
# Панель ввода чисел, которые оптимизатор получит как Settings.
from ui.control_panel import ControlPanel
# Панель сообщений о качестве геометрии и полноте картографических слоёв.
from ui.audit_panel import AuditPanel
# Панель целевого процента затенения.
from ui.goal_panel import GoalPanel
# Виджет карты Leaflet и его мост к Qt.
from ui.map_widget import MapWidget
# Панель сравнительных показателей алгоритмов.
from ui.results_panel import ResultsPanel


# Ищет введённое название через Nominatim и возвращает широту, долготу и подпись места.
def search_city(query: str) -> tuple[float, float, str]:
    # Формируем запрос Nominatim: искомая строка, формат JSON и только один лучший ответ.
    url = "https://nominatim.openstreetmap.org/search?" + urlencode({"q": query, "format": "json", "limit": 1})
    # Указываем User-Agent приложения, чтобы сервис мог распознать источник запроса.
    request = Request(url, headers={"User-Agent": "HeatShield/1.0 (educational urban heat planning)"})
    # Открываем ответ с таймаутом 15 секунд, чтобы поиск не зависал бесконечно.
    with urlopen(request, timeout=15) as response:
        # Декодируем тело ответа как JSON-список найденных мест.
        results = json.load(response)
    # Пустой ответ означает, что такую фразу сервис не нашёл.
    if not results:
        # Возвращаем понятную пользователю ошибку, которую обработает сигнал ошибки Worker.
        raise ValueError("Место не найдено. Уточните название города или района.")
    # Отдаём широту, долготу и полное подпись-имя первого результата.
    return float(results[0]["lat"]), float(results[0]["lon"]), results[0]["display_name"]


# Главное окно соединяет форму выбора, параметры плана, показатели и интерактивную карту.
class MainWindow(QMainWindow):
    # Конструктор создаёт окно и соединяет пользовательские действия с обработчиками.
    def __init__(self) -> None:
        # Инициализируем базовое окно Qt до настройки его содержимого.
        super().__init__()
        # Задаём заголовок окна с названием приложения.
        self.setWindowTitle(f"{APP_NAME} — озеленение городов")
        # Устанавливаем удобный начальный размер в пикселях.
        self.resize(1460, 900)
        # bounds будет хранить выбранный прямоугольник в градусах: юг, запад, север, восток.
        self.bounds: tuple[float, float, float, float] | None = None
        # analysis хранит загруженные слои, кандидатов и рассчитанные планы либо None до анализа.
        self.analysis: Analysis | None = None
        # Флаг предотвращает несколько одновременных тяжёлых пересчётов.
        self._rerun_running = False
        # Ссылка позволяет отбросить результат для уже сменившегося участка.
        self._rerun_source: Analysis | None = None
        # Берём общий пул потоков Qt, чтобы сетевые вычисления не блокировали окно.
        self.pool = QThreadPool.globalInstance()
        # Создаём встроенную карту Leaflet и делаем её дочерним виджетом окна.
        self.map = MapWidget(self)
        # Сигнал прямоугольника карты вызывает обработчик выбора границ участка.
        self.map.bridge.rectangle_selected.connect(self._rectangle_selected)
        # Сигнал щелчка по кандидату переключает его включение в ручном плане.
        self.map.bridge.candidate_clicked.connect(self._toggle_candidate)
        # Сигнал перетаскивания маркера передаёт координаты для безопасного переноса дерева.
        self.map.bridge.candidate_move_requested.connect(self._move_tree)
        # Левая панель содержит поля и вкладки; ширина фиксирована для устойчивого макета.
        panel = QWidget()
        # 440 пикселей оставляют достаточно места для полей и таблицы, не забирая всю ширину карты.
        panel.setFixedWidth(440)
        # Располагаем содержимое панели вертикально с внутренними отступами и промежутками.
        layout = QVBoxLayout(panel)
        # Четыре числа задают отступы слева, сверху, справа и снизу в пикселях.
        layout.setContentsMargins(12,12,12,10)
        # Восемь пикселей отделяют соседние блоки интерфейса.
        layout.setSpacing(8)
        # Заголовок приложения выделен стилем, чтобы его было легко заметить.
        title = QLabel("HeatShield")
        title.setStyleSheet("font-size:26px;font-weight:700;color:#176b4d")
        # Добавляем крупное название в верхнюю часть левой панели.
        layout.addWidget(title)
        # Подзаголовок кратко объясняет назначение окна и указывает источник картографических данных.
        subtitle = QLabel("Планирование городской тени · данные OpenStreetMap")
        # Перенос нужен, если окно пользователя уже начального размера.
        subtitle.setWordWrap(True)
        # Ставим описание непосредственно под названием программы.
        layout.addWidget(subtitle)

        # Вкладки делят длинную форму на выбор места, параметры и результаты.
        self.tabs=QTabWidget()
        # Отдаём вкладкам свободное пространство панели, чтобы прокручиваемые страницы росли.
        layout.addWidget(self.tabs,1)
        # Вспомогательная функция строит прокручиваемую вкладку и возвращает место для её элементов.
        def tab_page(name:str)->QVBoxLayout:
            # Создаём страницу вкладки и её вертикальный контейнер.
            # Создаём пустую страницу и вертикальную компоновку с промежутком между элементами.
            page=QWidget();page_layout=QVBoxLayout(page);page_layout.setSpacing(10)
            # Отступы отделяют содержимое страницы от края окна.
            page_layout.setContentsMargins(12,12,12,12)
            # Прокрутка позволяет просматривать высокую форму на небольшом экране.
            # Настраиваем область прокрутки: она растягивается, но её рамка не занимает место.
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            # Размещаем страницу внутри прокрутки и добавляем её как именованную вкладку.
            scroll.setWidget(page);self.tabs.addTab(scroll,name)
            # Возвращаем компоновку, в которую вызывающий код добавит поля.
            return page_layout

        # Вкладка «Участок» собирает способы выбрать область для географического анализа.
        location_layout=tab_page("Участок")

        # Поиск по названию города запускает запрос к OpenStreetMap.
        # Создаём рамку и форму для поля поиска города.
        city_group=QGroupBox("Поиск места"); city_form=QFormLayout(city_group)
        # В поле можно ввести название населённого пункта или района.
        # Создаём поле и показываем в нём пример допустимого поискового запроса.
        self.city_query=QLineEdit(); self.city_query.setPlaceholderText("Например: Алматы, Казахстан")
        # Нажатие кнопки вызывает _search_city, который проверит запрос и запустит Worker.
        # Создаём кнопку и соединяем её сигнал clicked с обработчиком поиска.
        self.city_button=QPushButton("Найти город или район"); self.city_button.clicked.connect(self._search_city)
        # Добавляем строку ввода и кнопку в группу поиска.
        # Сначала ставим поле, затем кнопку, после чего добавляем группу на вкладку места.
        city_form.addRow(self.city_query);city_form.addRow(self.city_button);location_layout.addWidget(city_group)
        # Отдельная группа позволяет выбрать точку из общей или короткой ссылки Google Maps.
        # Отдельная рамка отделяет ввод ссылки карты от поиска по названию.
        link_group=QGroupBox("Google Maps");link_form=QFormLayout(link_group)
        # Поле принимает URL карты, из которого парсер извлечёт GPS-координаты.
        # Поле показывает пример ссылки Google Maps, которую умеет распознавать парсер.
        self.url=QLineEdit();self.url.setPlaceholderText("https://www.google.com/maps/@...")
        # Кнопка передаёт ссылку обработчику, который распознаёт обычные и сокращённые URL.
        # Кнопка подключает обработчик, который извлечёт из URL координаты участка.
        link_button=QPushButton("Выбрать по ссылке");link_button.clicked.connect(self._from_link)
        # Вставляем поле и кнопку в форму ссылки.
        # Располагаем URL и кнопку друг под другом и добавляем группу на страницу.
        link_form.addRow(self.url);link_form.addRow(link_button);location_layout.addWidget(link_group)
        # Здесь можно задать широту, долготу и радиус прямоугольной области анализа.
        # Создаём форму, в которой координаты и радиус задаются отдельно.
        coord_group=QGroupBox("Координаты и радиус");coord_form=QFormLayout(coord_group)
        # Широта ограничена диапазоном от Южного до Северного полюса.
        # Поле широты принимает дробные градусы и показывает начальный центр Алматы.
        self.lat=QDoubleSpinBox();self.lat.setRange(-90,90);self.lat.setDecimals(6);self.lat.setValue(43.2389)
        # Долгота ограничена всем диапазоном земного шара.
        # Поле долготы использует диапазон всего земного шара и тот же начальный город.
        self.lon=QDoubleSpinBox();self.lon.setRange(-180,180);self.lon.setDecimals(6);self.lon.setValue(76.8897)
        # Список радиусов задаёт расстояние от центра до краёв участка в метрах.
        # Выбираем один из трёх радиусов в метрах; при старте установлен средний вариант.
        self.radius=QComboBox();self.radius.addItems(["250 м","500 м","1000 м"]);self.radius.setCurrentIndex(1)
        # Любая ручная правка координаты инвалидирует ранее выбранные границы.
        self.lat.valueChanged.connect(self._coordinates_edited)
        # Изменение долготы также требует подтверждения выбора участка.
        self.lon.valueChanged.connect(self._coordinates_edited)
        # При смене радиуса нужно заново сформировать географическую область.
        self.radius.currentIndexChanged.connect(self._coordinates_edited)
        # Кнопка превращает текущие координаты и радиус в границы для анализа.
        # Кнопка подтверждает координаты и запускает построение прямоугольных границ участка.
        coord_button=QPushButton("Выбрать по координатам");coord_button.clicked.connect(self._from_coordinates)
        # Добавляем три поля с поясняющими подписями.
        # Каждому полю назначаем русскую подпись и добавляем пару в форму.
        for name,widget in (("Широта",self.lat),("Долгота",self.lon),("Радиус",self.radius)):
            # Цикл создаёт три строки формы: подпись слева, связанное поле справа.
            coord_form.addRow(name,widget)
        # Кнопка добавляется отдельно под тремя полями, затем группа попадает на вкладку.
        coord_form.addRow(coord_button);location_layout.addWidget(coord_group)
        # Информационная метка объясняет, как выделить область прямо на карте.
        # Метка показывает инструкцию до выбора и сведения о границах после него.
        self.info=QLabel("На карте: зажмите Shift и выделите прямоугольник мышью.")
        # Переносим подсказку по ширине и размещаем её на вкладке участка.
        self.info.setWordWrap(True);location_layout.addWidget(self.info)
        # Кнопка открывает диалог чтения ранее сохранённого JSON-сценария.
        # Кнопка открытия подключена к методу, который восстановит план из JSON-файла.
        load_button=QPushButton("Открыть сохранённый сценарий");load_button.clicked.connect(self._load)
        # Кнопка открытия находится рядом со способами выбора территории.
        location_layout.addWidget(load_button)
        # Пользователь может дополнить неполную OSM-карту местной инвентаризацией.
        self.local_tree_file = ""
        # Второй файл позволяет учесть известные запреты посадки.
        self.local_restricted_file = ""
        # Эта кнопка выбирает точки существующих деревьев или линии рядов деревьев.
        tree_button = QPushButton("Добавить существующие деревья · GeoJSON")
        tree_button.clicked.connect(self._choose_local_trees)
        location_layout.addWidget(tree_button)
        # Эта кнопка выбирает полигоны мест, где посадку нельзя предлагать.
        restricted_button = QPushButton("Добавить запретные зоны · GeoJSON")
        restricted_button.clicked.connect(self._choose_local_restricted)
        location_layout.addWidget(restricted_button)
        # Подпись постоянно показывает, какие дополнительные источники выбраны.
        self.local_data_info = QLabel("Дополнительные данные: не загружены")
        self.local_data_info.setWordWrap(True)
        location_layout.addWidget(self.local_data_info)
        # Растяжка прижимает элементы выбора места к верху и заполняет свободное место снизу.
        location_layout.addStretch()

        # Вкладка планирования содержит веса, бюджет и целевой процент затенения.
        planning_layout=tab_page("Параметры")
        # ControlPanel создаёт числовые поля оптимизатора.
        self.controls=ControlPanel();planning_layout.addWidget(self.controls)
        # GoalPanel задаёт цель тени и показывает, достиг ли её текущий план.
        self.goal=GoalPanel();planning_layout.addWidget(self.goal)
        # Свободное место уходит под настройками, чтобы они не растягивались по высоте.
        planning_layout.addStretch()
        # Таймер срабатывает один раз после паузы, чтобы серия быстрых изменений не запускала много пересчётов.
        self._goal_timer=QTimer(self);self._goal_timer.setSingleShot(True)
        # По окончании задержки сигнал timeout запускает актуальный повторный расчёт.
        self._goal_timer.timeout.connect(self._rerun)
        # Изменение процента цели планирует пересчёт через таймер.
        self.goal.target.valueChanged.connect(self._schedule_goal_rerun)

        # Вкладка результатов показывает показатели, аудит и экспорт.
        results_layout=tab_page("Результаты")
        # ResultsPanel визуализирует численные метрики двух планов.
        self.results=ResultsPanel();results_layout.addWidget(self.results)
        # AuditPanel показывает нарушения геометрии и предупреждения о качестве данных.
        self.audit=AuditPanel();results_layout.addWidget(self.audit)
        # Экспорт недоступен, пока анализ не создал данные для сохранения.
        self.save_button=QPushButton("Сохранить сценарий и экспорт");self.save_button.setEnabled(False)
        # Нажатие кнопки вызывает диалог сохранения всех форматов результата.
        self.save_button.clicked.connect(self._save);results_layout.addWidget(self.save_button)
        # Уточняем, что OSM — источник данных, а местоположения деревьев требуют проверки на месте.
        note=QLabel("© OpenStreetMap contributors. Места посадки предварительные: проверьте собственность, коммуникации, грунт и существующие деревья.")
        note.setWordWrap(True);note.setStyleSheet("color:#61756b;font-size:9pt")
        # Внизу результатов оставляем напоминание об источнике и необходимости полевой проверки.
        results_layout.addWidget(note);results_layout.addStretch()

        # Главная кнопка недоступна, пока пользователь не выбрал корректный участок.
        self.analyze_button=QPushButton("Анализировать территорию");self.analyze_button.setEnabled(False)
        # Имя объекта позволяет общей теме приложения выделить эту главную кнопку.
        self.analyze_button.setObjectName("primaryAction")
        # Щелчок вызывает загрузку OSM и анализ в фоновом потоке.
        self.analyze_button.clicked.connect(self._analyze);layout.addWidget(self.analyze_button)
        # Повторная оптимизация выключена до появления первого результата анализа.
        self.rerun_button=QPushButton("Повторить оптимизацию");self.rerun_button.setEnabled(False)
        # Кнопка запускает пересчёт с текущими весами и выбранной целью.
        self.rerun_button.clicked.connect(self._rerun_and_show);layout.addWidget(self.rerun_button)

        # Правая часть окна содержит панель карты и сам встроенный Leaflet.
        map_panel=QWidget();map_layout=QVBoxLayout(map_panel)
        # Убираем внешние поля, чтобы карта занимала всю доступную площадь.
        map_layout.setContentsMargins(0,0,0,0);map_layout.setSpacing(0)
        # Верхняя панель карты показывает сводку участка и переключатель результата.
        toolbar=QWidget();toolbar.setObjectName("mapToolbar")
        # Горизонтально располагаем подпись-сводку и флажок отображения тени.
        toolbar_layout=QHBoxLayout(toolbar);toolbar_layout.setContentsMargins(14,6,14,6)
        # До выбора участка подсказываем пользователю, где его можно задать.
        self.map_summary=QLabel("Выберите участок на карте или во вкладке «Участок»")
        # Имя связывает надпись со стилем панели карты из main.py.
        self.map_summary.setObjectName("mapSummary")
        # Коэффициент 1 разрешает сводке растянуться и оставить флажок справа.
        toolbar_layout.addWidget(self.map_summary,1)
        # Флажок включает или скрывает слой будущей тени; по умолчанию результат виден.
        self.after=QCheckBox("Показать результат · После");self.after.setChecked(True)
        # Сигнал toggled передаёт bool напрямую в MapWidget.show_after.
        self.after.toggled.connect(self.map.show_after)
        # Переключатель расположен рядом с кратким итогом, над самой картой.
        toolbar_layout.addWidget(self.after)
        # Ставим панель над картой, а карте отдаём всё оставшееся место по высоте.
        map_layout.addWidget(toolbar);map_layout.addWidget(self.map,1)
        # Корневой макет ставит левую панель рядом с картой и убирает промежутки по краям.
        root=QWidget();row=QHBoxLayout(root);row.setContentsMargins(0,0,0,0);row.setSpacing(0)
        # Левая панель сохраняет заданную ширину, карта занимает оставшуюся ширину окна.
        row.addWidget(panel);row.addWidget(map_panel,1)
        # Назначаем корневой виджет центральным содержимым главного окна.
        self.setCentralWidget(root)
        # Сразу объясняем, что сетевые поиск и анализ требуют подключения к интернету.
        self.statusBar().showMessage("Для поиска и анализа нужен интернет.")

    # Выполняет медленную функцию в фоновом потоке и связывает сигналы успеха/ошибки с UI.
    def _run_worker(self,function,done,*args)->None:
        # Worker вызывает функцию с переданными аргументами отдельно от основного UI-потока.
        worker=Worker(function,*args)
        # При успехе передаём результат в нужный обработчик, при исключении показываем сообщение.
        worker.signals.finished.connect(done);worker.signals.failed.connect(self._error)
        # Запускаем задачу через пул потоков, не замораживая окно во время загрузки.
        self.pool.start(worker)

    # Возвращает кнопки в рабочее состояние и показывает пользователю причину сбоя.
    def _error(self,message:str)->None:
        # Возвращаем кнопки в рабочее состояние после ошибки фоновой операции.
        self.analyze_button.setEnabled(self.bounds is not None);self.city_button.setEnabled(True)
        # Показываем краткий текст ошибки в строке состояния окна.
        self.statusBar().showMessage("Ошибка: "+message)
        # Диалог даёт полное сообщение и совет проверить сеть/уменьшить участок.
        QMessageBox.warning(self,"Не удалось выполнить операцию",message+"\nПроверьте интернет и попробуйте меньшую территорию.")

    # Проверяет запрос названия и запускает фоновый поиск города.
    def _search_city(self)->None:
        # Убираем пробелы по краям перед проверкой названия.
        query=self.city_query.text().strip()
        # Слишком короткий запрос вряд ли поможет найти нужное место.
        if len(query)<2:self._error("Введите название города или района.");return
        # Пока выполняется запрос, отключаем кнопку от повторных нажатий.
        self.city_button.setEnabled(False)
        # Сообщаем, что приложение ищет адрес через сервис OpenStreetMap.
        self.statusBar().showMessage("Ищем место в OpenStreetMap…")
        # Запускаем поиск вне UI-потока; _city_found обработает координаты при успехе.
        self._run_worker(search_city,self._city_found,query)

    # Принимает результат поиска, заполняет GPS-поля и выбирает радиусную область.
    def _city_found(self,result:tuple)->None:
        # Получаем из ответа широту, долготу и название найденной записи.
        lat,lon,name=result;self.city_button.setEnabled(True)
        # Подставляем координаты в поля и формируем область выбранного радиуса.
        self.lat.setValue(lat);self.lon.setValue(lon);self._from_coordinates()
        # Показываем пользователю, какое именно место нашлось.
        self.statusBar().showMessage("Найдено: "+name)

    # Сбрасывает выбранную область и результаты, если пользователь изменил входные GPS-поля.
    def _coordinates_edited(self,*_args)->None:
        # При ручной правке координат прежние границы больше не соответствуют видимым значениям.
        # Сбрасываем старые границы: после ручной правки участка кнопка анализа должна отключиться.
        self.bounds=None
        # Старые координаты больше не выбраны, поэтому анализ запускать нельзя.
        self.analyze_button.setEnabled(False)
        # Подсказка объясняет, какое действие требуется после ручного редактирования широты.
        self.info.setText("Координаты изменены. Нажмите «Выбрать по координатам», чтобы задать участок.")
        # Верхняя строка карты перестаёт показывать показатели прежней территории.
        self.map_summary.setText("Участок не выбран")
        # Убираем подсветку старой области с карты и старые результаты её анализа.
        self.map.clear_selection()
        # Удаляем старые слои и цифры, чтобы их нельзя было принять за новые результаты.
        self._clear_analysis()

    # Удаляет результат прошлого анализа из модели, карты и панелей.
    def _clear_analysis(self)->None:
        # Если результата нет, очищать нечего и не нужно трогать виджеты.
        if self.analysis is None:return
        # Удаляем старый Analysis, чтобы он не выдавался за результат нового участка.
        self.analysis=None
        # У нового участка ещё нет подсчитанных допустимых мест.
        self.controls.available_candidates=None
        self.controls._update_capacity()
        # Останавливаем отложенный пересчёт цели, который мог относиться к старому анализу.
        self._goal_timer.stop()
        # Сохранять или пересчитывать больше нечего до завершения следующего анализа.
        self.rerun_button.setEnabled(False);self.save_button.setEnabled(False)
        # Очищаем старые геометрии карты, числовые показатели и статус аудита.
        self.map.clear_analysis()
        # Обнуляем старые числа, чтобы интерфейс не показывал метрики предыдущей области.
        self.results.reset()
        # Возвращаем аудиту исходную подсказку, так как проверки для новой области ещё нет.
        self.audit.label.setText("Проверка появится после анализа OSM.")
        # Объясняем, что цель будет проверяться только после следующего анализа.
        self.goal.status.setText("Сначала выполните анализ выбранного участка.")

    # Обрабатывает длинную ссылку Google Maps сразу, короткую сначала раскрывает в фоне.
    def _from_link(self)->None:
        # Считываем URL и удаляем случайные пробелы вокруг него.
        url=self.url.text().strip()
        # Короткие ссылки нельзя разобрать локально: сначала разрешаем их до конечного URL в фоне.
        if url.startswith("https://maps.app.goo.gl/") or url.startswith("https://goo.gl/maps/"):
            # Короткую ссылку нужно сначала запросить у сервиса, поэтому сообщаем о сетевой операции.
            self.statusBar().showMessage("Раскрываем короткую ссылку Google Maps…")
            # Передаём URL в фоновый Worker; результат вернётся в _link_found.
            self._run_worker(resolve_short_google_url,self._link_found,url)
            # Выходим, чтобы не пытаться разбирать ещё не раскрытую короткую ссылку.
            return
        # Для обычной ссылки пытаемся извлечь GPS-точку; ошибку формата показываем диалогом.
        # Извлекаем координаты прямо из длинного URL без сетевого запроса.
        try:lat,lon=parse_google_maps_url(url)
        # При ошибке формата показываем причину и прекращаем обработку этой ссылки.
        except ValueError as exc:QMessageBox.warning(self,"Не удалось прочитать ссылку",str(exc));return
        # Подставляем найденную точку и строим вокруг неё участок выбранного радиуса.
        self.lat.setValue(lat);self.lon.setValue(lon);self._from_coordinates()

    # Получает координаты раскрытой короткой ссылки и передаёт их в выбор области.
    def _link_found(self,result:tuple)->None:
        # Результат раскрытия короткой ссылки уже содержит широту и долготу.
        lat,lon=result;self.lat.setValue(lat);self.lon.setValue(lon);self._from_coordinates()

    # Проверяет введённую точку и строит прямоугольник из центра и радиуса.
    def _from_coordinates(self)->None:
        # Проверяем введённые градусы, чтобы исключить координаты за пределами Земли.
        lat,lon=validate_coordinates(self.lat.value(),self.lon.value())
        # Читаем радиус в метрах из подписи вроде «500 м».
        # Парсим число метров; приближённо один градус широты равен 111 320 метрам.
        radius=int(self.radius.currentText().split()[0]);dlat=radius/111320
        # Один градус долготы сужается к полюсам, поэтому делим поправку на cos(широты).
        dlon=radius/(111320*max(.01,math.cos(math.radians(lat))))
        # Переводим радиус в приближённые градусные смещения для границ прямоугольника.
        self._set_bounds(lat-dlat,lon-dlon,lat+dlat,lon+dlon)
        # При корректной площади перемещаем Leaflet к центру выбранного участка.
        if self.bounds:self.map.focus_area(lat,lon,radius)

    # Принимает из карты четыре границы, пришедшие через сигнал MapBridge.
    def _rectangle_selected(self,south:float,west:float,north:float,east:float)->None:
        # Границы приходят из JS-карты через сигнал bridge и становятся выбранной областью.
        self._set_bounds(south,west,north,east,source="прямоугольник на карте")
        # Возвращаем пользователя на первую вкладку, где отображается информация об участке.
        self.tabs.setCurrentIndex(0)

    # Проверяет площадь и координаты, а затем сохраняет границы, пригодные для анализа.
    def _set_bounds(self,south:float,west:float,north:float,east:float,source:str="координаты и радиус")->None:
        # Новый участок делает прежний расчёт устаревшим, поэтому сначала очищаем его.
        self._clear_analysis()
        # Приближённо считаем площадь прямоугольника в км² с поправкой долготы по средней широте.
        area=abs((north-south)*111.32*(east-west)*111.32*math.cos(math.radians((south+north)/2)))
        # Проверяем порядок и диапазоны GPS-координат, положительную площадь и верхний лимит проекта.
        if not (-90<=south<north<=90 and -180<=west<east<=180 and 0<area<=MAX_AREA_KM2+1e-6):
            # Невалидная область не может быть проанализирована; выключаем действие и снимаем выделение.
            self.bounds=None;self.analyze_button.setEnabled(False)
            # Снимаем прежнюю подсветку, чтобы на карте не осталась отклонённая рамка.
            self.map.clear_selection()
            # Показываем рассчитанный размер и допустимый предел, после чего выходим из обработчика.
            self.info.setText(f"Площадь {area:.2f} км². Допустимо: 0–{MAX_AREA_KM2:g} км².");return
        # Сохраняем проверенные границы в согласованном порядке для последующих шагов анализа.
        self.bounds=(south,west,north,east)
        # Когда границы нарисованы мышью, обновляем поля центра без запуска их сигналов очистки.
        if source=="прямоугольник на карте":
            # QSignalBlocker подавляет valueChanged на время программной установки координат.
            with QSignalBlocker(self.lat), QSignalBlocker(self.lon):
                # Записываем среднюю широту прямоугольника в поле центра.
                self.lat.setValue((south+north)/2)
                # Записываем среднюю долготу прямоугольника, не запуская сигнал очистки анализа.
                self.lon.setValue((west+east)/2)
        # Показываем источник выбора, центр, углы и примерную площадь участка.
        self.info.setText(f"Выбран: {source}\nЦентр: {(south+north)/2:.5f}, {(west+east)/2:.5f}\nЮЗ: {south:.5f}, {west:.5f}\nСВ: {north:.5f}, {east:.5f}\nПлощадь: {area:.2f} км²")
        # Краткая сводка над картой напоминает площадь и следующее действие.
        self.map_summary.setText(f"Выбран участок · {area:.2f} км² · нажмите «Анализировать территорию»")
        # Разрешаем запуск только после успешной проверки границ.
        self.analyze_button.setEnabled(True)

    # Запускает загрузку OSM и полный расчёт для выбранных границ.
    def _analyze(self)->None:
        # Без выбранной области анализ невозможен; защита также нужна при вызове из кода.
        if self.bounds is None:return
        # Блокируем повторный старт той же операции и показываем статус ожидания.
        self.analyze_button.setEnabled(False)
        # Показываем, что сейчас загружаются данные и выполняется геометрический расчёт.
        self.statusBar().showMessage("Загружаем OSM и анализируем. Это может занять несколько минут…")
        # Загружаем OSM и рассчитываем кандидатов в фоне; передаём снимок границ и текущие настройки.
        # Файлы считываются в фоновом потоке вместе с OSM-данными.
        self._run_worker(analyze,self._analysis_done,self.bounds,self._settings(),self.local_tree_file,self.local_restricted_file)

    # Выбирает файл с координатами существующих деревьев.
    def _choose_local_trees(self)->None:
        # Отмена диалога сохраняет прежний выбор.
        filename,_=QFileDialog.getOpenFileName(self,"Инвентаризация деревьев","","GeoJSON (*.geojson *.json)")
        # При новом файле прежний план становится устаревшим.
        if filename:self.local_tree_file=filename;self._local_data_changed()

    # Выбирает файл с полигонами, где посадка запрещена.
    def _choose_local_restricted(self)->None:
        # Пользователь выбирает собственный проверенный слой ограничений.
        filename,_=QFileDialog.getOpenFileName(self,"Запретные зоны","","GeoJSON (*.geojson *.json)")
        # Изменённые ограничения требуют нового полного анализа.
        if filename:self.local_restricted_file=filename;self._local_data_changed()

    # Обновляет подпись и сбрасывает план после смены местных данных.
    def _local_data_changed(self)->None:
        # Короткое имя дерева читается легче, чем полный путь.
        tree_name=Path(self.local_tree_file).name if self.local_tree_file else "нет"
        # Аналогично показываем имя файла с запретными местами.
        restricted_name=Path(self.local_restricted_file).name if self.local_restricted_file else "нет"
        # Оба источника отображаются рядом с кнопками выбора.
        self.local_data_info.setText(f"Деревья: {tree_name}\nЗапретные зоны: {restricted_name}")
        # Старые рекомендации нельзя сохранять после изменения исходных данных.
        self._clear_analysis()
        # При уже выбранном участке разрешаем новый запуск анализа.
        self.analyze_button.setEnabled(self.bounds is not None)

    # Собирает настройки из полей панели и добавляет значение цели затенения.
    def _settings(self)->Settings:
        # Берём значения панели и добавляем выбранную пользователем цель процента затенения.
        return replace(self.controls.settings(),target_shade_percent=self.goal.target.value())

    # Применяет ответ фонового анализа только если выбранные границы за это время не изменились.
    def _analysis_done(self,analysis:Analysis)->None:
        # Пока шла загрузка, пользователь мог изменить участок; не показываем старые данные поверх нового.
        if self.bounds!=analysis.bounds or (self.local_tree_file,self.local_restricted_file)!=analysis.source_files:
            # Показываем сообщение на 10 секунд, так как устаревший ответ не будет применён.
            self.statusBar().showMessage("Участок или дополнительные файлы изменились во время загрузки. Старый результат отброшен.",10000)
            # Отбрасываем устаревший ответ и сообщаем, почему он не показан.
            return
        # Сохраняем свежий объект анализа и передаём картографические слои в Leaflet.
        self.analysis=analysis;self.map.set_layers(analysis.layers,analysis.free_layer)
        # Обновляем маркеры, показатели и аудит, а затем снова включаем действия с результатом.
        # Перерисовываем результат и снова разрешаем запуск анализа для другого участка.
        self._show_analysis();self.analyze_button.setEnabled(True)
        # Разрешаем повторный расчёт и экспорт только после получения пригодного Analysis.
        self.rerun_button.setEnabled(True);self.save_button.setEnabled(True)
        # Открываем вкладку метрик, чтобы результат был виден сразу после завершения.
        self.tabs.setCurrentIndex(2)
        # Уточняем число геометрически построенных точек и необходимость проверки на месте.
        self.statusBar().showMessage(f"Готово: {len(analysis.candidates)} геометрических кандидатов. Точки требуют проверки на месте.")

    # Передаёт текущие кандидаты/план карте и обновляет все панели результата.
    def _show_analysis(self)->None:
        # Защита от обновления виджетов, когда расчёт ещё не завершён или уже очищен.
        if self.analysis is None:return
        # Подсказка учитывает также сценарий, открытый из сохранённого JSON.
        self.controls.available_candidates=len(self.analysis.candidates)
        self.controls._update_capacity()
        # Отправляем JS-карте кандидатов, выбранные id и настройки для отображения плана.
        self.map.set_candidates(self.analysis.candidates,self.analysis.greedy.ids,self.analysis.settings)
        # Обновляем сводные метрики, цель и проверку геометрии.
        self.results.show_metrics(self.analysis.metrics)
        # Передаём метрики панели, которая отдельно показывает прогресс к цели затенения.
        self.goal.show_metrics(self.analysis.metrics)
        # Отображаем замечания проверки данных и столкновения с препятствиями.
        self.audit.show_audit(self.analysis.metrics)
        # Показываем над картой число деревьев и долю новой тени от площади участка.
        self.map_summary.setText(f"{len(self.analysis.greedy.ids)} деревьев · новая тень {self.analysis.metrics['greedy']['study_area_shaded_percent']:.3f}% участка")

    # Пересчитывает план и открывает вкладку метрик.
    def _rerun_and_show(self)->None:
        # Пересчитываем текущий план с последними настройками пользователя.
        self._rerun()
        # После нажатия показываем вкладку с итогами, если результат всё ещё существует.
        if self.analysis is not None:self.tabs.setCurrentIndex(2)

    # Пересчитывает автоматический план на уже загруженных данных с текущими настройками.
    def _rerun(self)->None:
        # Без завершённого анализа повторно выбирать не из чего.
        if self.analysis is None:return
        # Пока идёт старый расчёт, новые настройки будут взяты после его завершения.
        if self._rerun_running:return
        # Запоминаем конкретный исходный анализ.
        self._rerun_source=self.analysis
        # Копируем настройки на момент запуска.
        settings=self._settings()
        # Запрещаем параллельный запуск оптимизатора на тех же точках.
        self._rerun_running=True
        # Сотни деревьев могут считаться несколько секунд, поэтому показываем статус.
        self.statusBar().showMessage("Подбираем места для деревьев в фоне…")
        # Worker выполняет тяжёлый алгоритм вне потока интерфейса.
        worker=Worker(rerun,self.analysis,settings)
        # По завершении проверяем актуальность результата.
        worker.signals.finished.connect(self._rerun_done)
        # При ошибке также освобождаем возможность повторного запуска.
        worker.signals.failed.connect(self._rerun_failed)
        # Добавляем задачу в общий пул фоновых потоков.
        self.pool.start(worker)

    # Применяет только расчёт, который соответствует текущему участку и настройкам.
    def _rerun_done(self,result:Analysis)->None:
        # Фоновая задача завершилась, поэтому следующий запуск разрешён.
        self._rerun_running=False
        # Если открыт другой участок, старый план не показываем.
        if self.analysis is not self._rerun_source:return
        # Если настройки успели поменяться, считаем план заново с последними значениями.
        if self._settings()!=result.settings:
            # Повторный запуск идёт после завершения предыдущего Worker.
            self._rerun()
            return
        # Сохраняем итоговый план как текущий.
        self.analysis=result
        # Обновляем маркеры и показатели в главном потоке интерфейса.
        self._show_analysis()
        # Сообщаем фактический итог, который может быть меньше запроса.
        self.statusBar().showMessage(f"План обновлён: {len(result.greedy.ids)} деревьев из {len(result.candidates)} возможных мест.",10000)

    # Освобождает интерфейс после ошибки фоновой оптимизации.
    def _rerun_failed(self,message:str)->None:
        # Без сброса этого флага кнопка перестала бы работать после ошибки.
        self._rerun_running=False
        # Общий обработчик показывает пользователю причину.
        self._error(message)

    # Откладывает повторный расчёт, чтобы серия изменений цели дала только один запуск.
    def _schedule_goal_rerun(self)->None:
        # До первого анализа цель можно менять, но пересчитывать ещё нечего.
        if self.analysis is not None:
            # Сообщаем, что новый процент цели запустит обновление плана.
            self.goal.status.setText("Пересчитываем план для новой цели…")
            # Запускаем/перезапускаем одноразовый таймер; быстрые движения поля схлопнутся в один пересчёт.
            self._goal_timer.start(300)

    # Добавляет выбранную на карте точку в план или удаляет её и проверяет ограничения.
    def _toggle_candidate(self,candidate_id:int)->None:
        # Карта может прислать щелчок лишь после анализа, когда кандидаты уже известны.
        if self.analysis is None:return
        # Ручное изменение не должно потеряться после завершения фоновой оптимизации.
        if self._rerun_running:self.statusBar().showMessage("Дождитесь завершения оптимизации.",5000);return
        # Принимаем актуальные настройки, включая цель тени.
        settings=self._settings()
        # Если веса изменились с последнего расчёта, сначала обновляем базовый план.
        if settings!=self.analysis.settings:
            # Перестраиваем исходный автоматический план с новыми параметрами перед ручным переключением точки.
            self.analysis=rerun(self.analysis,settings)
        # Копируем текущие номера, чтобы добавить или убрать выбранную точку без изменения исходного списка.
        ids=list(self.analysis.greedy.ids)
        # Повторный щелчок снимает выбор; первый щелчок добавляет точку в ручной список.
        if candidate_id in ids:ids.remove(candidate_id)
        # Если точки в списке ещё нет, добавляем её как новое дерево ручного плана.
        else:ids.append(candidate_id)
        # Переводим границу участка в метры, потому что проверка расстояний и площадей работает в проекции.
        study_area,_=projected_boundary(self.analysis.bounds)
        # Проверяем вручную собранный набор по лимиту количества, бюджету и минимальным расстояниям.
        try:custom=evaluate_selection(self.analysis.candidates,ids,settings,study_area)
        # Если выбор нарушает ограничение, показываем причину и сохраняем предыдущий корректный план.
        except ValueError as exc:QMessageBox.information(self,"Ограничение размещения",str(exc));return
        # Считаем метрики нового плана рядом с прежним случайным контрольным планом.
        metrics=compare(custom,self.analysis.random,self.analysis.settings,self.analysis.candidates,self.analysis.route_lines,study_area)
        # Помечаем способ формирования, чтобы отчёт различал ручной выбор и автоматический greedy.
        metrics["plan_method"]="manual"
        # Переносим сведения аудита и обновляем число проверенных выбранных позиций.
        metrics["audit"]={**self.analysis.metrics.get("audit",{}),"selected_checked":len(custom.ids)} if self.analysis.metrics.get("audit") else {}
        # Создаём Analysis-копию с новым ручным планом и метриками, не меняя остальные загруженные данные.
        self.analysis=replace(self.analysis,greedy=custom,metrics=metrics)
        # Обновляем карту и показатели по ручному выбору.
        self._show_analysis()

    # Привязывает перетаскивание дерева к ближайшему проверенному кандидату и пересчитывает план.
    def _move_tree(self,old_id:int,lat:float,lon:float)->None:
        # Перемещение маркера имеет смысл только для существующего результата анализа.
        if self.analysis is None:return
        # Перенос блокируется только на время фонового пересчёта того же плана.
        if self._rerun_running:self.statusBar().showMessage("Дождитесь завершения оптимизации.",5000);return
        # Берём настройки, действующие в момент перемещения.
        settings=self._settings()
        # Перед проверкой новой позиции синхронизируем план, если пользователь изменил его параметры.
        if settings!=self.analysis.settings:
            # Сначала пересчитываем план с новыми весами, чтобы перенос сравнивался с актуальным сценарием.
            self.analysis=rerun(self.analysis,settings)
        # Сохраняем старые показатели, чтобы сообщить пользователю изменение после переноса.
        previous=self.analysis.metrics["greedy"]
        # Геометрия участка нужна для точного расчёта пересечений крон и границы.
        study_area,_=projected_boundary(self.analysis.bounds)
        # Ищем ближайшую подтверждённую геометрией точку и проверяем ограничения всего плана.
        try:
            # Передаём план и координату маркера; функция выберет ближайшего кандидата и вернёт расстояние привязки.
            custom,new_id,snap_distance=move_tree(self.analysis.candidates,self.analysis.greedy.ids,
                                                  # Старый id и новая широта/долгота задают перемещаемое дерево и место курсора.
                                                  old_id,lat,lon,settings,study_area=study_area)
        # Если позиция далека от кандидата или нарушает расстояние, отменяем действие и восстанавливаем карту.
        except ValueError as exc:
            # Строка состояния кратко объясняет, почему дерево не удалось перенести.
            self.statusBar().showMessage("Перенос отменён: "+str(exc),10000)
            # Перерисовываем старую допустимую позицию вместо оставшегося в браузере жеста.
            self._show_analysis()
            # Не продолжаем расчёт метрик: невалидный перенос оставил прежний план без изменений.
            return
        # При успешном переносе заново сравниваем план с контрольным случайным вариантом.
        metrics=compare(custom,self.analysis.random,settings,self.analysis.candidates,self.analysis.route_lines,study_area)
        # Указываем в метриках, что пользователь вручную изменил расположение.
        metrics["plan_method"]="manual"
        # Пересохраняем число прошедших аудит выбранных позиций.
        metrics["audit"]={**self.analysis.metrics.get("audit",{}),"selected_checked":len(custom.ids)} if self.analysis.metrics.get("audit") else {}
        # Читаем новые метрики, затем заменяем план внутри неизменённого Analysis.
        current=metrics["greedy"]
        # Записываем принятый ручной план и его свежие метрики в объект текущего анализа.
        self.analysis=replace(self.analysis,greedy=custom,metrics=metrics)
        # Обновляем отображение карты и панелей после принятого перемещения.
        self._show_analysis()
        # Показываем id заменённого кандидата, точность привязки и изменения тени/полезности.
        self.statusBar().showMessage(
            f"Дерево #{old_id} → кандидат #{new_id} (привязка {snap_distance:.1f} м). "
            # Отображаем изменение затенённой доли площади в процентных пунктах относительно старого плана.
            f"Δ новой тени на участке: {current['study_area_shaded_percent']-previous.get('study_area_shaded_percent',0):+.3f} п.п.; "
            # Последняя часть строки показывает изменение условной полезности и длительность сообщения в миллисекундах.
            f"Δ условной пользы: {current['relative_utility']-previous['relative_utility']:+.2f}.",15000)

    # Записывает текущий план в JSON, GeoJSON, CSV и изображения сравнения до/после.
    def _save(self)->None:
        # До анализа нет состояния, которое можно сохранить.
        if self.analysis is None:return
        # Диалог позволяет выбрать имя базового JSON-файла для комплекта результатов.
        filename,_=QFileDialog.getSaveFileName(self,"Сохранить сценарий",str(Path.home()/"HeatShield-сценарий.json"),"JSON (*.json)")
        # Пустое имя означает, что пользователь закрыл диалог без сохранения.
        if not filename:return
        # Приводим расширение к JSON и сохраняем ссылку на текущий Analysis.
        path=Path(filename).with_suffix(".json");a=self.analysis
        # Записываем полный сценарий и отдельные форматы, удобные для GIS, таблиц и просмотра.
        try:
            # JSON хранит границы, оценки, планы, слои, маршруты и настройки для повторного открытия.
            save_scenario(path,a.bounds,a.candidates,a.settings,a.greedy,a.random,a.metrics,a.layers,a.free_layer,a.route_lines)
            # GeoJSON содержит географические объекты кандидатов и выбранного плана.
            save_geojson(path.with_suffix(".geojson"),a.candidates,a.greedy)
            # CSV предназначен для просмотра данных о выбранных точках в табличном редакторе.
            save_csv(path.with_suffix(".csv"),a.candidates,a.greedy)
            # Сохраняем карту «до»: показываем исходные слои и не включаем выбранные кроны.
            save_map_png(path.with_name(path.stem+"-до.png"),a.bounds,{**a.layers,"free":a.free_layer},a.candidates,[])
            # Сохраняем карту «после» с выбранными id, чтобы сравнить эффект плана.
            save_map_png(path.with_name(path.stem+"-после.png"),a.bounds,{**a.layers,"free":a.free_layer},a.candidates,a.greedy.ids)
            # Сообщаем, что все форматы комплекта записаны.
            self.statusBar().showMessage("Сохранены JSON, GeoJSON, CSV и карты PNG.")
        # Ошибки записи файлов переводим в понятный интерфейсный диалог.
        except OSError as exc:self._error(str(exc))

    # Читает сценарий, проверяет его версию и восстанавливает модель и виджеты окна.
    def _load(self)->None:
        # Открываем диалог выбора JSON-сценария.
        filename,_=QFileDialog.getOpenFileName(self,"Открыть сценарий","","JSON (*.json)")
        # Отмена диалога не должна менять текущее состояние окна.
        if not filename:return
        # Читаем и проверяем содержимое; допустимые ошибки будут показаны пользователю ниже.
        try:
            # Декодируем сохранённый JSON в словарь Python.
            data=json.loads(Path(filename).read_text(encoding="utf-8"))
            # Версия схемы говорит, как интерпретировать поля этого файла.
            version=data.get("schema_version")
            # Старые неизвестные и будущие несовместимые версии не загружаем.
            if version not in (1,2,3):raise ValueError("Неподдерживаемая версия сценария.")
            # Копируем настройки перед удалением устаревшего поля старой схемы.
            settings_data=dict(data["settings"])
            # Это поле больше не используется актуальной моделью Settings.
            settings_data.pop("target_reduction_percent",None)
            # Создаём объекты настроек и кандидатов из сохранённых словарей.
            settings=Settings(**settings_data);candidates=[Candidate(**c) for c in data["candidates"]]
            # Восстанавливаем проекцию границы участка, чтобы пересчитать площади в метрах.
            study_area,_=projected_boundary(tuple(data["bounds"]))
            # Читаем сохранённые составы и время планов.
            stored_g=Placement(**data["greedy"]);stored_r=Placement(**data["random"])
            # Проверяем выбранные id на актуальных правилах и обновляем метрики геометрии.
            g=replace(evaluate_selection(candidates,stored_g.ids,settings,study_area),elapsed_s=stored_g.elapsed_s)
            # Ту же проверку выполняем для контрольного случайного плана.
            r=replace(evaluate_selection(candidates,stored_r.ids,settings,study_area),elapsed_s=stored_r.elapsed_s)
            # Маршрутов может не быть в старых версиях сценария, поэтому используем пустой список.
            route_lines=data.get("route_lines",[])
            # Пересчитываем общие показатели по загруженным кандидатам и планам.
            metrics=compare(g,r,settings,candidates,route_lines,study_area)
            # Восстанавливаем метку способа и данные аудита, если они были сохранены.
            metrics["plan_method"]=data.get("metrics",{}).get("plan_method","greedy")
            # Если сценарий сохранил данные аудита, возвращаем их в панель проверок.
            metrics["audit"]=data.get("metrics",{}).get("audit",{})
            # Собираем все части сценария в рабочую структуру Analysis.
            # Собираем восстановленные данные в объект, который используют обработчики окна.
            self.analysis=Analysis(tuple(data["bounds"]),data.get("layers",{}),data.get("free_layer",{}),
                                   # В объект также входят кандидаты, параметры, оба плана, метрики и маршруты.
                                   candidates,settings,g,r,metrics,route_lines)
            # Слои уже сохранены внутри сценария, пути прошлых внешних файлов не нужны.
            self.local_tree_file=""
            self.local_restricted_file=""
            self.local_data_info.setText("Дополнительные файлы не выбраны; сохранённые слои уже внутри сценария")
            # Синхронизируем выбранную область, поля настроек и целевой процент с прочитанным файлом.
            # Фиксируем границы, затем восстанавливаем поля настроек и целевой процент из файла.
            self.bounds=self.analysis.bounds;self.controls.set_settings(settings);self.goal.set_target(settings.target_shade_percent)
            # Разворачиваем четыре границы, чтобы показать координаты и площадь в интерфейсе.
            south,west,north,east=self.bounds
            # Изменяем поля центра без реакции _coordinates_edited, иначе только что загруженный анализ очистился бы.
            with QSignalBlocker(self.lat), QSignalBlocker(self.lon):
                # Устанавливаем обе координаты центра; блокировщики не дают очистить загруженный анализ.
                self.lat.setValue((south+north)/2);self.lon.setValue((west+east)/2)
            # Рассчитываем ту же приближённую площадь, которую использует выбор границ.
            area=abs((north-south)*111.32*(east-west)*111.32*math.cos(math.radians((south+north)/2)))
            # Показываем, что область восстановлена из сценария, вместе с координатами и площадью.
            self.info.setText(f"Выбран: сохранённый сценарий\nЦентр: {(south+north)/2:.5f}, {(west+east)/2:.5f}\nЮЗ: {south:.5f}, {west:.5f}\nСВ: {north:.5f}, {east:.5f}\nПлощадь: {area:.2f} км²")
            # Передаём загруженные слои в Leaflet и обновляем маркеры с метриками.
            # Сначала передаём Leaflet геометрические слои, затем маркеры и показатели текущего плана.
            self.map.set_layers(self.analysis.layers,self.analysis.free_layer);self._show_analysis()
            # Масштабируем карту так, чтобы целиком показать восстановленные границы участка.
            self.map.focus_bounds(south,west,north,east)
            # Открываем результаты и включаем кнопки доступных действий.
            self.tabs.setCurrentIndex(2)
            # После восстановления доступны новый анализ, пересчёт и повторный экспорт.
            self.analyze_button.setEnabled(True);self.rerun_button.setEnabled(True);self.save_button.setEnabled(True)
            # При устаревшей версии предупреждаем, что новые показатели были пересчитаны по имеющимся данным.
            if version<3:self.statusBar().showMessage("Сценарий старой версии: показатели пересчитаны по новой модели, для обновления исходных оценок выполните новый анализ.",15000)
        # Ошибки чтения, обязательных полей или типов показываем как отказ загрузки сценария.
        except (OSError,ValueError,TypeError,KeyError) as exc:self._error("Не удалось загрузить сценарий: "+str(exc))
