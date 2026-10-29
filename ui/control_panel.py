"""Optimization controls kept apart from map code."""
# Панель собирает параметры алгоритма из полей ввода и превращает их в Settings.

# Поля SpinBox позволяют вводить числа, а форма связывает подписи с соответствующими полями.
from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QGroupBox, QSpinBox, QLabel

# Settings — структура параметров, которую использует оптимизатор.
from core.optimizer import Settings


# Группа числовых полей, из которых пользователь собирает настройки оптимизатора.
class ControlPanel(QGroupBox):
    # parent позволяет встроить панель в другое окно Qt и управляет её временем жизни.
    def __init__(self, parent=None) -> None:
        # Создаём группу с заголовком, который виден пользователю над элементами формы.
        super().__init__("Параметры озеленения", parent)
        # Форма располагает подписью слева и полем ввода справа.
        form = QFormLayout(self)
        # Число деревьев: разрешаем целое значение от 0 до 500 и начинаем с 20.
        self.trees = QSpinBox()
        # Алгоритм создаёт не больше 1800 геометрических кандидатов; ввод выше 100 разрешён.
        self.trees.setRange(0, 1800)
        # Начальный план рассчитан на двадцать деревьев.
        self.trees.setValue(20)
        # Бюджет: целые тенге, изменение шагом 10 000 и начальное значение 200 000 ₸.
        self.budget = QDoubleSpinBox()
        # Разрешаем бюджет от нуля до миллиарда тенге.
        self.budget.setRange(0, 1e9)
        # Не показываем копейки, так как бюджет в приложении задаётся целыми тенге.
        self.budget.setDecimals(0)
        # Кнопки изменения значения будут прибавлять или вычитать 10 000 тенге.
        self.budget.setSingleStep(10000)
        # Устанавливаем стартовый общий бюджет в 200 000 тенге.
        self.budget.setValue(200000)
        # Показываем денежную единицу рядом с вводимым числом.
        self.budget.setSuffix(" ₸")
        # Цена одного дерева должна быть минимум 1 ₸; это значение участвует в бюджетном лимите.
        self.cost = QDoubleSpinBox()
        # Диапазон цены не допускает нулевую стоимость и ограничивает верхнее значение 100 миллионами тенге.
        self.cost.setRange(1, 1e8)
        # Цена отображается без дробной части тенге.
        self.cost.setDecimals(0)
        # Начальная цена одного дерева составляет 10 000 тенге.
        self.cost.setValue(10000)
        # Добавляем суффикс валюты, чтобы единицу было видно при вводе.
        self.cost.setSuffix(" ₸")
        # Минимальная дистанция между стволами измеряется в метрах и по умолчанию равна 12 м.
        self.distance = QDoubleSpinBox()
        # Разрешаем промежуток от нуля до ста метров.
        self.distance.setRange(0, 100)
        # Стартовое безопасное расстояние между деревьями — двенадцать метров.
        self.distance.setValue(12)
        # Показываем, что поле измеряет длину в метрах.
        self.distance.setSuffix(" м")
        # Вес жары задаёт её важность для плана; шаг 0,25 позволяет тонко менять приоритет.
        self.heat = QDoubleSpinBox()
        # Вес может быть отключён нулём или усилен максимум до десяти.
        self.heat.setRange(0, 10)
        # Изменяем вес жары шагами по четверти единицы.
        self.heat.setSingleStep(.25)
        # По умолчанию жаре назначен обычный вес 1.
        self.heat.setValue(1)
        # Вес пешеходного фактора работает как относительный приоритет маршрутов.
        self.pedestrian = QDoubleSpinBox()
        # Пешеходный приоритет может быть от нуля до десяти.
        self.pedestrian.setRange(0, 10)
        # Шаг в четверть помогает настраивать приоритет постепенно.
        self.pedestrian.setSingleStep(.25)
        # По умолчанию пешеходный фактор равен по весу остальным факторам.
        self.pedestrian.setValue(1)
        # Вес дефицита зелени определяет, насколько алгоритм предпочитает менее озеленённые места.
        self.green = QDoubleSpinBox()
        # Диапазон от нуля до десяти позволяет выключить или усилить этот фактор.
        self.green.setRange(0, 10)
        # Вес дефицита зелени меняется шагом 0,25.
        self.green.setSingleStep(.25)
        # Начальный вес зелени установлен равным единице.
        self.green.setValue(1)
        # Seed задаёт начальное состояние случайного алгоритма, чтобы его результат повторялся.
        self.seed = QSpinBox()
        # Разрешаем целое значение seed от нуля до 999 999.
        self.seed.setRange(0, 999999)
        # Значение 42 делает случайный контрольный план воспроизводимым.
        self.seed.setValue(42)
        # Добавляем все пары подпись/поле в форму в том порядке, в котором их увидит пользователь.
        for label, widget in (("Деревьев",self.trees),("Бюджет",self.budget),("Цена за дерево",self.cost),
                              # Продолжаем список полей: расстояние и вес теплового фактора.
                              ("Мин. расстояние",self.distance),("Приоритет жары",self.heat),
                              # Последние пары отвечают за пешеходов, зелень и воспроизводимый random seed.
                              ("Приоритет пешеходов",self.pedestrian),("Дефицит зелени",self.green),("Random seed",self.seed)):
            # Каждое поле получает подпись, поясняющую пользователю значение вводимого числа.
            form.addRow(label, widget)
        # Эта подпись показывает денежный предел ещё до долгого анализа карты.
        self.capacity = QLabel()
        # До анализа количество геометрически допустимых кандидатов неизвестно.
        self.available_candidates: int | None = None
        # Перенос строк сохраняет удобство узкой боковой панели.
        self.capacity.setWordWrap(True)
        # Подписываемся на изменения трёх полей, определяющих доступное число деревьев.
        for widget in (self.trees, self.budget, self.cost):
            widget.valueChanged.connect(self._update_capacity)
        # Выводим подсказку сразу под параметрами.
        form.addRow("Предел плана", self.capacity)
        # Заполняем её значениями по умолчанию при создании интерфейса.
        self._update_capacity()

    # Показывает, сколько деревьев помещается в бюджет и сколько денег нужно для полного запроса.
    def _update_capacity(self) -> None:
        # Поле стоимости никогда не допускает ноль, поэтому деление безопасно.
        affordable = int(self.budget.value() // self.cost.value())
        # План ограничен меньшим из запроса и денежного предела.
        actual = min(self.trees.value(), affordable)
        # Умножение даёт бюджет, который нужен для запрошенного числа.
        needed = self.trees.value() * self.cost.value()
        # Места на карте проверяются отдельно после скачивания OSM.
        # Отдельно показываем размер найденной сетки, если карта уже разобрана.
        places = "Места проверяются после анализа." if self.available_candidates is None else f"Геометрических кандидатов: {self.available_candidates}."
        # Подпись сообщает все основные причины меньшего результата.
        self.capacity.setText(f"Запрошено {self.trees.value()}; бюджет позволяет {affordable}; к подбору не больше {actual}. Для полного запроса нужно {needed:,.0f} ₸. {places}")

    # Создаёт объект Settings из текущих значений всех полей ввода.
    def settings(self) -> Settings:
        # Читаем число деревьев, бюджет, цену и расстояние в порядке полей Settings.
        return Settings(self.trees.value(),self.budget.value(),self.cost.value(),self.distance.value(),
                        # Последними передаём веса жары, пешеходов, зелени и seed случайного алгоритма.
                        self.heat.value(),self.pedestrian.value(),self.green.value(),self.seed.value())

    # Заполняет поля значениями из Settings, например при загрузке сценария.
    def set_settings(self, settings: Settings) -> None:
        # Сопоставляем поля ввода соответствующим значениям, чтобы загрузить сохранённую конфигурацию.
        for widget, value in ((self.trees,settings.trees),(self.budget,settings.budget),(self.cost,settings.cost_per_tree),
                              # В этой части связываем минимальное расстояние и вес жары с их полями формы.
                              (self.distance,settings.minimum_distance_m),(self.heat,settings.heat_weight),
                              # Завершаем соответствия весами пешеходов/зелени и целым значением seed.
                              (self.pedestrian,settings.pedestrian_weight),(self.green,settings.green_weight),(self.seed,settings.seed)):
            # Показываем сохранённое значение в поле; диапазон виджета остаётся ограничителем ввода.
            widget.setValue(value)
