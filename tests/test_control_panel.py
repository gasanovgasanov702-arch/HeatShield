# Проверяем пользовательский ввод числа деревьев выше ста и понятный денежный предел.
import os
# QApplication необходим для создания настоящих полей интерфейса Qt.
from PySide6.QtWidgets import QApplication

# Панель параметров содержит реальные поля числа, бюджета и стоимости.
from ui.control_panel import ControlPanel


# При достаточном бюджете поле должно передать оптимизатору все 150 деревьев.
def test_tree_count_above_one_hundred_and_budget_hint():
    # В автоматическом прогоне окно Qt не требуется выводить на экран.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # Переиспользуем существующее приложение, если тест уже создал его.
    app = QApplication.instance() or QApplication([])
    # Создаём ту же панель, которую показывает главное окно.
    panel = ControlPanel()
    # Пользователь просит больше ста деревьев.
    panel.trees.setValue(150)
    # При бюджете по умолчанию реально оплачивается только двадцать.
    assert panel.trees.value() == 150 and panel.settings().limit() == 20
    # Подсказка обязана показать причину ограничения без запуска карты.
    assert "бюджет позволяет 20" in panel.capacity.text()
    # Увеличиваем бюджет ровно до суммы за 150 деревьев.
    panel.budget.setValue(1_500_000)
    # Теперь денежный предел больше не срезает выбранное количество.
    assert panel.settings().limit() == 150
    # Подсказка обновляется сразу, без повторного открытия окна.
    assert "к подбору не больше 150" in panel.capacity.text()
    # Держим ссылку на QApplication до конца теста, чтобы Qt не удалил объекты раньше.
    assert app is not None
