"""Точка входа: Python начинает запуск HeatShield именно с этого файла."""

# logging — стандартная библиотека Python для сообщений о работе программы и ошибках.
import logging
# sys нужен, чтобы передать Qt аргументы командной строки и корректно завершить процесс.
import sys

# QFont задаёт шрифт всего приложения, чтобы надписи были единообразными.
from PySide6.QtGui import QFont
# QApplication управляет жизненным циклом и событиями всех окон Qt.
from PySide6.QtWidgets import QApplication

# MainWindow — наше главное окно с картой, вкладками и кнопками.
from ui.main_window import MainWindow


# Функция возвращает числовой код завершения: 0 обычно означает штатное закрытие.
def main() -> int:
    # Показываем сообщения уровня INFO и выше вместе со временем и типом сообщения.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Создаём объект Qt и передаём ему аргументы запуска из sys.argv.
    app = QApplication(sys.argv)
    # Имя приложения будет видно системе Windows и некоторым элементам интерфейса.
    app.setApplicationName("HeatShield")
    # Fusion даёт одинаковый базовый вид элементов на разных версиях Windows.
    app.setStyle("Fusion")
    # Segoe UI 10 пунктов делает обычные подписи узнаваемыми для пользователя Windows.
    app.setFont(QFont("Segoe UI", 10))
    # Строка ниже задаёт цвета и отступы для всех виджетов через Qt Style Sheets.
    # Внутри тройных кавычек находится язык оформления QSS, а не исполняемый Python.
    app.setStyleSheet("""
        QMainWindow, QScrollArea, QWidget { background: #f6f8f7; color: #17332c; }
        QGroupBox { border: 1px solid #cfddd4; border-radius: 9px; margin-top: 11px;
                    padding: 10px 7px 7px; font-weight: 600; background: #ffffff; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
        QPushButton { background: #e5f3ea; border: 1px solid #abcdb8; border-radius: 6px;
                      padding: 7px 9px; font-weight: 600; }
        QPushButton:hover { background: #d0edda; }
        QPushButton:disabled { background: #f0f1f0; color: #87958d; border-color: #d8dfda; }
        QPushButton#primaryAction { background: #176b4d; color: white; border-color: #176b4d; padding: 10px; }
        QPushButton#primaryAction:hover { background: #0f563d; }
        QPushButton#primaryAction:disabled { background: #dce9e1; color: #779283; border-color: #dce9e1; }
        QTabWidget::pane { border: 1px solid #cfddd4; border-radius: 8px; background: #ffffff; }
        QTabBar::tab { background: #e8f0ea; color: #476659; padding: 9px 14px; margin-right: 3px;
                       border-top-left-radius: 7px; border-top-right-radius: 7px; }
        QTabBar::tab:selected { background: #ffffff; color: #125c42; font-weight: 700; }
        QWidget#mapToolbar { background: #ffffff; border-bottom: 1px solid #d5e1d9; }
        QLabel#mapSummary { font-weight: 600; color: #285940; }
        QLabel#resultHeadline { background: #e9f5ec; color: #155b40; border-radius: 6px;
                                padding: 11px; font-weight: 700; }
        QLabel#metricValue { font-weight: 600; color: #234a39; }
        QLabel#comparisonNote { background: #f5f2e8; border-radius: 5px; padding: 9px; }
        QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox { background: white; border: 1px solid #bacbc0;
                       border-radius: 5px; padding: 5px; min-height: 20px; }
        QStatusBar { background: #eaf1ec; }
    """)
    # Только после создания QApplication можно безопасно создавать главное окно Qt.
    window = MainWindow()
    # Показываем окно; без show() приложение работало бы, но пользователь ничего не увидел бы.
    window.show()
    # Цикл Qt ждёт кликов, ввода и сигналов; когда окно закрывается, возвращает код выхода.
    return app.exec()


# Условие истинно при прямом запуске «python main.py», но ложно при импорте модуля в тестах.
if __name__ == "__main__":
    # Передаём Windows код завершения, который вернул цикл приложения.
    raise SystemExit(main())
