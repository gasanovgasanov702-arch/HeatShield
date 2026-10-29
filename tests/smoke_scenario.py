"""Ручная проверка GUI на включённом сценарии; сеть не нужна."""
# Path нужен, чтобы найти JSON примера независимо от папки, из которой запустили проверку.
from pathlib import Path
# Короткое ожидание даёт фоновому оптимизатору время завершиться без зависания теста.
import time
# QTimer закроет GUI через заданное время; Qt widgets создают приложение и диалог выбора файла.
from PySide6.QtCore import QTimer
# QApplication запускает Qt, QFileDialog здесь подменяется для чтения заранее известного JSON.
from PySide6.QtWidgets import QApplication, QFileDialog
# MainWindow — проверяемое окно приложения; move_tree и projected_boundary воспроизводят перенос и геометрию.
from ui.main_window import MainWindow
# move_tree проверяет допустимость ручного перемещения с теми же ограничениями, что использует приложение.
from core.optimizer import move_tree
# projected_boundary переводит выбранный прямоугольник в метрическую геометрию для проверки перемещения.
from core.geodesy import projected_boundary

# Запускаем Qt-приложение без аргументов командной строки.
app=QApplication([])
# Создаём главное окно, чьи вкладки, кнопки и результаты будут проверяться.
window=MainWindow()
# Готовим локальный JSON центрального Алматы; он используется вместо выбора файла пользователем.
example=Path(__file__).resolve().parents[1]/"examples"/"almaty"/"almaty_center.json"
# Подменяем диалог выбора так, чтобы окно получило путь к нашему примеру без ручного клика.
QFileDialog.getOpenFileName=lambda *args,**kwargs:(str(example),"JSON (*.json)")
# Загружаем пример через штатный обработчик окна.
window._load()
# Показываем число кандидатов; -1 означает, что анализ не создался.
print("candidates",len(window.analysis.candidates) if window.analysis else -1,flush=True)
# Показываем, разрешено ли экспортировать рассчитанный результат.
print("export enabled",window.save_button.isEnabled(),flush=True)
# Вкладка с индексом 2 должна быть результатами после загрузки готового сценария.
assert window.tabs.currentIndex()==2
# Обе сравниваемые стратегии должны сообщать 20 выбранных деревьев.
assert window.results.values["trees"][0].text()=="20"
# Второй показатель относится ко второй стратегии сравнения, которая также должна выбрать 20 деревьев.
assert window.results.values["trees"][1].text()=="20"
# Печатаем, что экран результатов сравнивает оба метода.
print("results tab compares both methods",flush=True)
# Устанавливаем цель затенения 25%, чтобы проверить запуск пересчёта по новой цели.
window.goal.set_target(.25)
# Повторно рассчитываем планы с обновлённой целью.
window._rerun()
# Фоновый Worker сообщает о результате через события Qt, поэтому их нужно обрабатывать.
deadline=time.monotonic()+30
# Проверка ограничена тридцатью секундами, чтобы ошибка не повесила весь прогон.
while window._rerun_running and time.monotonic()<deadline:
    # Доставляем сигнал завершения Worker в главный поток интерфейса.
    app.processEvents()
    # Небольшая пауза не нагружает процессор при ожидании.
    time.sleep(.02)
# Если расчёт так и не завершился, дымовой тест сообщает о проблеме.
assert not window._rerun_running
# Выводим число деревьев жадного плана и достигнута ли цель согласно метрикам.
print("goal trees",len(window.analysis.greedy.ids),"reached",window.analysis.metrics["goal"]["reached"],flush=True)
# Получаем полигон исследования в метрической проекции; исходный код системы координат здесь не нужен.
region,_=projected_boundary(window.analysis.bounds)
# Перебираем уже выбранные деревья, чтобы найти одно, которое можно вручную перенести.
for old_id in window.analysis.greedy.ids:
    # Перебираем возможные новые точки размещения.
    for candidate in window.analysis.candidates:
        # Не пробуем точку, которая уже занята другим деревом в текущем плане.
        if candidate.id in window.analysis.greedy.ids:continue
        # Сначала проверяем правила переноса оптимизатора без изменения окна.
        try:
            # Передаём текущий план, id переносимого дерева и координаты пробной точки; исключение означает запрет переноса.
            move_tree(window.analysis.candidates,window.analysis.greedy.ids,old_id,
                      # Широта/долгота кандидата задают цель в градусах; settings и region задают правила и исследуемую область.
                      candidate.lat,candidate.lon,window.analysis.settings,study_area=region)
        # Некоторые точки не подходят из-за расстояния/границ; пробуем следующую.
        except ValueError:continue
        # Выполняем допустимый перенос через обработчик GUI.
        window._move_tree(old_id,candidate.lat,candidate.lon)
        # Показываем текущий метод плана и попал ли выбранный кандидат в итоговый список.
        print("manual move",window.analysis.metrics["plan_method"],candidate.id in window.analysis.greedy.ids,flush=True)
        # Достаточно проверить один успешный перенос.
        break
    # Если у старого дерева не нашлось подходящего места, продолжаем с другим старым деревом.
    else:
        # Цикл не нашёл ни одной допустимой новой точки для old_id, поэтому проверяем следующий id дерева.
        continue
    # После первого успешного переноса внешний цикл тоже можно завершить.
    break
# Сохраняем ссылку на анализ перед изменением выбранной области, чтобы проверить устаревший ответ.
old_analysis=window.analysis
# Имитируем выбор прямоугольника карты: юго-западные и северо-восточные широта/долгота в градусах.
window._rectangle_selected(42.30595,69.59215,42.31981,69.61300)
# Убеждаемся, что окно сохранило все четыре границы выбранной области в правильном порядке.
assert window.bounds==(42.30595,69.59215,42.31981,69.61300)
# Центральная широта прямоугольника равна среднему южной и северной границ с точностью 0.00001°.
assert abs(window.lat.value()-42.31288)<.00001
# Центральная долгота равна среднему западной и восточной границ с той же точностью.
assert abs(window.lon.value()-69.602575)<.00001
# При смене зоны старый анализ сбрасывается, поэтому экспорт снова запрещён.
assert window.analysis is None and not window.save_button.isEnabled()
# После выбора новой зоны интерфейс возвращается на первую вкладку.
assert window.tabs.currentIndex()==0
# Старые числа о количестве деревьев заменяются длинным тире как признак отсутствия результата.
assert window.results.values["trees"][0].text()=="—"
# Поздний ответ предыдущего анализа не должен перезаписывать актуальное пустое состояние окна.
window._analysis_done(old_analysis)
# Устаревший ответ обработчика не должен вернуть в окно анализ старого прямоугольника.
assert window.analysis is None
# Показываем координаты центра, синхронизированные с выбранным прямоугольником.
print("rectangle synchronizes coordinates",window.lat.value(),window.lon.value(),flush=True)
# Меняем широту вручную; прежние границы области теперь не соответствуют введённому центру.
window.lat.setValue(40.2389)
# Анализ нельзя запускать, пока пользователь не выбрал новые границы для отредактированных координат.
assert window.bounds is None and not window.analyze_button.isEnabled()
# Обработчик ввода координат пересчитывает/сбрасывает область после ручного изменения поля.
window._from_coordinates()
# Проверяем, что выбранная область существует и её средняя широта совпадает с введённой (допуск 0.000001°).
assert window.bounds is not None and abs((window.bounds[0]+window.bounds[2])/2-40.2389)<1e-6
# Сообщаем, что координаты требуют повторного выбора зоны.
print("edited coordinates require reselection",flush=True)
# Загружаем сценарий ещё раз, чтобы проверить заполнение координат из файла.
window._load()
# Загруженный сценарий должен снова содержать рассчитанный анализ.
assert window.analysis is not None
# Поле широты интерфейса должно совпасть с центром границ сценария с точностью 1e-6 градуса.
assert abs(window.lat.value()-(window.bounds[0]+window.bounds[2])/2)<1e-6
# Печатаем подтверждение синхронизации при загрузке.
print("loaded scenario synchronizes coordinates",flush=True)
# Даём окну 2 секунды на завершение обновления, после чего закрываем Qt-приложение.
QTimer.singleShot(2000,app.quit)
# Запускаем цикл событий Qt, чтобы окно и асинхронные обработчики успели отработать.
app.exec()
