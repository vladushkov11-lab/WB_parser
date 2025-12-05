import gspread
from google.oauth2.service_account import Credentials

from datetime import datetime
import logging
data = [{'link': 'https://www.wildberries.ru/catalog/487635202/detail.aspx', 'seller': 'Super Express'}, 
        {'link': 'https://www.wildberries.ru/catalog/438835997/detail.aspx', 'seller': 'Greatxin'}, 
        {'link': 'https://www.wildberries.ru/catalog/487446682/detail.aspx', 'seller': 'Super Express'}, 
        {'link': 'https://www.wildberries.ru/catalog/548614635/detail.aspx', 'seller': 'Super Express'}, 
        {'link': 'https://www.wildberries.ru/catalog/486923821/detail.aspx', 'seller': 'YZF'}, 
        {'link': 'https://www.wildberries.ru/catalog/488178007/detail.aspx', 'seller': 'Super Express'}, 
        {'link': 'https://www.wildberries.ru/catalog/553810410/detail.aspx', 'seller': 'hou chun gui'}, 
        {'link': 'https://www.wildberries.ru/catalog/485600719/detail.aspx', 'seller': 'YZF'}, 
        {'link': 'https://www.wildberries.ru/catalog/504967793/detail.aspx', 'seller': 'Решение'}, 
        {'link': 'https://www.wildberries.ru/catalog/407995983/detail.aspx', 'seller': 'Super Express'}, 
        {'link': 'https://www.wildberries.ru/catalog/487919920/detail.aspx', 'seller': 'Super Express'}, 
        {'link': 'https://www.wildberries.ru/catalog/488164696/detail.aspx', 'seller': 'Super Express'}, 
        {'link': 'https://www.wildberries.ru/catalog/524343413/detail.aspx', 'seller': 'Vionex'}, 
        {'link': 'https://www.wildberries.ru/catalog/488064446/detail.aspx', 'seller': 'Super Express'},]
# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
def google_add(sellers_data, target_brand="Dazle", sheet_name="WB_parser"):
    target_brand = target_brand.lower()
    scope = ['https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive']

    credentials = Credentials.from_service_account_file("infinite-facet-479413-d8-1fdba68e8326.json", scopes=scope)
    client = gspread.authorize(credentials)
    print("📊 Подключение к Google Sheets...")
    try:
        client.open("Парсинг ВБ 2")
    except gspread.SpreadsheetNotFound:
        client.create("Парсинг ВБ 2")
        print("📊 Таблица создана")
    spreadsheet = client.open('Парсинг ВБ 2')
    print(f"Подключение успешно! Доступ к таблице: {spreadsheet.title}")
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(sheet_name, rows=1000, cols=200)
        print("Создан новый лист")
    headers = [
        "Ссылка",
        "Продавец",
    ]
    worksheet.append_row(headers)
    logger.info("📋 Заголовки добавлены")
    rows_to_add = []
    processed_count = 0
    for seller_info in sellers_data:
        try:
            row = [
                seller_info["link"],
                seller_info["seller"],
            ]
            seller = seller_info["seller"]
            link = seller_info["link"]
            seller = seller.lower()
            if seller == target_brand:
                continue
            elif seller != target_brand:
                rows_to_add.append(row)
                processed_count += 1
        except Exception as e:
            logger.warning(f"⚠️ Ошибка обработки записи: {e}")
            continue
    if rows_to_add:
        try:
            worksheet.append_rows(rows_to_add)
            logger.info(f"✅ Добавлено {processed_count} записей")
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении записей: {e}")
    else:
        logger.info("❌ Нет новых записей для добавления")
    total_rows = len(worksheet.get_all_values())
    logger.info(f"📋 Добавлено {total_rows} записей")
    return worksheet
