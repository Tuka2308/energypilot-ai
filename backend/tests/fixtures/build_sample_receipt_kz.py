"""Генератор синтетической квитанции ЭСО для тестов.

Пересобирает `sample_receipt_kz.pdf` с нуля (не редактирование поверх
оригинала): рисует сетку таблицы и вставляет текст как настоящий текстовый
слой — то есть born-digital PDF, который `page.find_tables()` разбирает так
же, как реальную "Ведомость потребления электроэнергии".

Персональные данные — вымышленные (Иванов И. И., вымышленный адрес). Все
числовые значения (суммы, показания, потребление, период, номер точки
учёта) совпадают с оригиналом, чтобы регрессионные тесты не менялись.

Запуск: python tests/fixtures/build_sample_receipt_kz.py
Требует только pymupdf (уже в requirements.txt).
"""

from pathlib import Path

import fitz  # PyMuPDF

OUT_PATH = Path(__file__).parent / "sample_receipt_kz.pdf"

# Кириллический шрифт (встроенные хелв/таймс PyMuPDF кириллицу не умеют).
FONT_FILE = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_NAME = "arial"

PAGE_W, PAGE_H = 842, 595  # A4 landscape

TITLE_LINES = [
    "Ведомость потребления электроэнергии №6081100/6",
    "за период: Июнь 2026",
    'Потребитель: 6081100, Иванов И. И., г. Астана, район "Есиль", ул. Мангилик Ел, д.1',
]

# 15 колонок как в оригинале; ширины подобраны, чтобы текст помещался.
COL_WIDTHS = [95, 45, 52, 58, 42, 55, 52, 42, 32, 32, 45, 52, 40, 58, 58]
ROW_HEIGHTS = [48, 22, 62, 16, 24, 16]

TABLE_LEFT = 30
TABLE_TOP = 120

# Строки таблицы. Числа идентичны оригиналу; изменены только ФИО/адрес в
# колонке 0 строки данных (вымышленные).
ROWS = [
    # Заголовок (строка 0)
    [
        "Точка учета, адрес подключения", "Комментарий", "ПУ, Сетевой район",
        "Вид расчета", "Зоны суток ПУ", "Период расчета", "Показания",
        "Разница * коэф.", "Потери", "", "Потреблено", "Дифференциация",
        "Тариф", "Начислено", "",
    ],
    # Подзаголовки (строка 1)
    ["", "", "", "", "", "", "", "", "ЛЭП", "Трансф", "", "", "", "Сумма без НДС", "Сумма с НДС"],
    # Данные (строка 2) — вымышленные ФИО/адрес, числа как в оригинале
    [
        'ИТ Х-142, Иванов Иван Иванович, ПС-Школьная, ТП-249, Р-5кВт, '
        'г. Астана, район "Есиль", ул. Мангилик Ел, д.1',
        "", "CK007760 14 (ФЛ)", "По показаниям уст.ПУ, Нет дифференциации",
        "нет", "26.05.26 26.06.26 31", "2 001 2 071", "70 * 1", "", "", "70",
        "нет 70", "22,040", "1 542,80", "1 789,65",
    ],
    # Итого
    ["Итого:", "", "", "", "", "", "", "", "", "", "70", "", "", "1 542,80", "1 789,65"],
    # Нет дифференциации
    ["Нет дифференциации", "", "", "", "", "", "", "", "", "", "70", "нет 70", "22,040", "1 542,80", "1 789,65"],
    # Всего
    ["Всего:", "", "", "", "", "", "", "", "", "", "70", "", "", "1 542,80", "1 789,65"],
]


def _col_x() -> list[float]:
    xs = [TABLE_LEFT]
    for w in COL_WIDTHS:
        xs.append(xs[-1] + w)
    return xs


def _row_y() -> list[float]:
    ys = [TABLE_TOP]
    for h in ROW_HEIGHTS:
        ys.append(ys[-1] + h)
    return ys


def build() -> None:
    doc = fitz.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)

    # Заголовок над таблицей.
    y = 40
    for i, line in enumerate(TITLE_LINES):
        page.insert_text(
            (TABLE_LEFT, y), line, fontname=FONT_NAME, fontfile=FONT_FILE,
            fontsize=11 if i == 0 else 9,
        )
        y += 22 if i == 0 else 18

    xs, ys = _col_x(), _row_y()
    table_bottom, table_right = ys[-1], xs[-1]

    # Сетка: вертикальные и горизонтальные линии — по ним find_tables()
    # находит ячейки.
    for x in xs:
        page.draw_line((x, ys[0]), (x, table_bottom), color=(0, 0, 0), width=0.6)
    for yy in ys:
        page.draw_line((xs[0], yy), (table_right, yy), color=(0, 0, 0), width=0.6)

    # Текст ячеек.
    for r, row in enumerate(ROWS):
        for c, value in enumerate(row):
            if not value:
                continue
            rect = fitz.Rect(xs[c] + 1.5, ys[r] + 1.5, xs[c + 1] - 1.5, ys[r + 1] - 1.5)
            page.insert_textbox(
                rect, value, fontname=FONT_NAME, fontfile=FONT_FILE,
                fontsize=6, align=fitz.TEXT_ALIGN_LEFT,
            )

    # Подвал (как в оригинале).
    page.insert_text(
        (TABLE_LEFT, table_bottom + 40), "Телефоны:",
        fontname=FONT_NAME, fontfile=FONT_FILE, fontsize=9,
    )
    page.insert_text(
        (TABLE_LEFT, PAGE_H - 20),
        "Ведомость потребления электроэнергии №6081100/6 стр.1",
        fontname=FONT_NAME, fontfile=FONT_FILE, fontsize=8,
    )

    doc.save(OUT_PATH)
    doc.close()
    print(f"saved {OUT_PATH}")


if __name__ == "__main__":
    build()
