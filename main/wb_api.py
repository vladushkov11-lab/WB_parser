import logging
import time
import requests
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import asyncio
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from gspread.exceptions import GSpreadException
import threading

# Глобальные переменные для управления процессом
stop_flag = False
captcha_detected = False
captcha_event = threading.Event()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Настройки Chrome
options = Options()
options.add_argument("--start-maximized")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--disable-infobars")
options.add_argument("--disable-extensions")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1500,900")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option('useAutomationExtension', False)

# Инициализация драйвера
try:
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => false});")
    wait = WebDriverWait(driver, 8)
    short_wait = WebDriverWait(driver, 3)
    logger.info("✅ Chrome драйвер инициализирован")
except Exception as e:
    logger.error(f"❌ Ошибка инициализации драйвера: {e}")
    driver = None

def check_stop_flag():
    """Проверяет флаг остановки и бросает исключение если нужно остановиться"""
    global stop_flag
    if stop_flag:
        raise Exception("Процесс остановлен пользователем")

def wait_for_captcha_resolution(max_wait_minutes=10):
    """Ждёт решения капчи пользователем"""
    global captcha_detected, captcha_event
    
    logger.warning("🚨 ОБНАРУЖЕНА КАПЧА! 🚨")
    logger.info("⏳ Ожидание решения капчи...")
    logger.info(f"🕐 Максимальное время ожидания: {max_wait_minutes} минут")
    logger.info("💡 Пожалуйста, решите капчу в браузере и нажмите Enter в консоли, когда закончите")
    
    try:
        captcha_detected = True
        result = captcha_event.wait(timeout=max_wait_minutes * 60)
        
        if result:
            logger.info("✅ Капча решена! Продолжаем работу...")
            captcha_detected = False
            captcha_event.clear()
            return True
        else:
            logger.warning("⏰ Время ожидания капчи истекло!")
            captcha_detected = False
            return False
            
    except Exception as e:
        logger.error(f"Ошибка при ожидании капчи: {e}")
        captcha_detected = False
        return False

def detect_captcha():
    """Проверяет наличие капчи на странице"""
    if not driver:
        return False
        
    try:
        captcha_selectors = [
            "//*[contains(text(), 'капча') or contains(text(), 'captcha')]",
            "//*[contains(text(), 'Я не робот') or contains(text(), 'не робот')]",
            "//iframe[contains(@src, 'captcha') or contains(@src, 'recaptcha')]",
            "//div[contains(@class, 'captcha')]",
            "//button[contains(text(), 'Проверить')]"
        ]
        
        for selector in captcha_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                if elements:
                    for element in elements:
                        if element.is_displayed():
                            logger.debug(f"🔍 Обнаружен элемент капчи: {selector}")
                            return True
            except Exception as e:
                logger.debug(f"Ошибка проверки селектора {selector}: {e}")
                continue
                
        return False
        
    except Exception as e:
        logger.error(f"Ошибка при детекции капчи: {e}")
        return False

def collect_products_until_upsell(brand, max_products=200, max_scroll_steps=30, scroll_pause=1):
    global stop_flag
    
    if not driver:
        raise Exception("❌ Драйвер не инициализирован")
        
    seen_links = set()
    stop_y = None
    
    try:
        check_stop_flag()
        driver.get("https://www.wildberries.ru/")
        logger.info(f"🌐 Открыта главная WB. Ищем бренд: {brand}")

        search_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='Найти на Wildberries']")))
        time.sleep(3)
        logger.info("🔍 Вводим поисковый запрос...")
        search_input.clear()
        search_input.send_keys(brand)
        search_input.send_keys(Keys.RETURN)
        logger.info("🔍 Поиск отправлен")

        # Ждём загрузки результатов поиска
        time.sleep(5)
        logger.info("🚀 Начинаем сбор товаров...")

        for step in range(max_scroll_steps):
            check_stop_flag()
            if len(seen_links) >= max_products:
                logger.info("✅ Достигнуто максимальное количество товаров — останавливаемся.")
                break

            logger.info(f"🔁 Прокрутка {step + 1} из {max_scroll_steps} | Найдено товаров: {len(seen_links)}")

            # Прокручиваем страницу
            driver.execute_script("window.scrollBy(0, window.innerHeight);")
            time.sleep(scroll_pause)

            # Ищем блок рекомендаций
            try:
                upsell_blocks = driver.find_elements(
                    By.XPATH,
                    "//h2[contains(text(), 'Вы недавно смотрели') or contains(text(), 'Возможно, вам понравится')]"
                )
                if upsell_blocks:
                    stop_y = driver.execute_script(
                        "return arguments[0].getBoundingClientRect().top + window.pageYOffset;", upsell_blocks[0]
                    )
                    logger.info(f"🛑 Найден блок 'Вы смотрели' на высоте {stop_y}px — останавливаем прокрутку.")
                    break
            except Exception as e:
                logger.debug(f"🔍 Проверка блока 'Вы смотрели'... (ошибка: {e})")

            # Собираем ссылки на товары
            try:
                links = driver.find_elements(By.XPATH, "//a[contains(@href, '/catalog/')]")
                
                logger.debug(f"🔍 Найдено {len(links)} ссылок с /catalog/")
                
                for link in links:
                    try:
                        check_stop_flag()
                        
                        href = link.get_attribute("href")
                        
                        if not href or "/catalog/" not in href:
                            continue

                        if "/detail.aspx" not in href:
                            continue

                        # Фильтрация по высоте
                        if stop_y:
                            try:
                                card_y = link.location['y']
                                if card_y >= stop_y:
                                    continue
                            except Exception as e:
                                logger.debug(f"Ошибка получения координаты: {e}")
                                continue

                        if not link.is_displayed():
                            continue

                        if href not in seen_links:
                            seen_links.add(href)
                            logger.debug(f"➕ Добавлен товар: {href}")
                            
                    except Exception as e:
                        continue

            except Exception as e:
                logger.warning(f"⚠️ Ошибка при сборе ссылок: {e}")
                
        filename = "products_wb.txt"
        with open(filename, "w", encoding="utf-8") as f:
            for link in seen_links:
                f.write(link + "\n")
        
        logger.info(f"💾 Ссылки сохранены в {filename}")
        logger.info(f"🎯 ИТОГО: {len(seen_links)} товаров собрано")
        return list(seen_links)

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return list(seen_links)

def get_seller_from_product_page():
    """
    Извлекает продавца с текущей страницы товара Wildberries
    """
    try:
        # ПРИОРИТЕТНЫЙ селектор - точно такой как указал пользователь
        priority_selectors = [
            # Конкретный селектор от пользователя
            "span.mo-typography.mo-typography_variant_description.mo-typography_variable-weight_description.sellerInfoNameDefaultText--qLwgq",
            # Вариации этого селектора
            "span[class*='sellerInfoNameDefaultText']",
            "span[class*='sellerInfoName']",
            "span[class*='sellerInfo']",
            # Частичные совпадения классов
            "span[class*='mo-typography'][class*='sellerInfoNameDefaultText']",
            "span[class*='seller'][class*='Info'][class*='Name']"
        ]
        

        for selector in priority_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    if element.is_displayed():
                        seller_text = element.text.strip()
                        if seller_text and len(seller_text) > 1:
                            return seller_text
            except Exception as e:
                logger.debug(f"Ошибка приоритетного селектора {selector}: {e}")
                continue
        try:
            # Ищем контейнер с информацией о продавце
            seller_containers = driver.find_elements(By.XPATH, 
                "//div[contains(@class, 'seller') or contains(@class, 'brand') or contains(@class, 'info')]//span[not(contains(@class, 'price'))]"
            )
            
            for container in seller_containers:
                if container.is_displayed():
                    text = container.text.strip()
                    if text and len(text) > 1 and not any(x in text.lower() for x in ['руб', '₽', 'цена', 'скидка', 'доставка']):
                        logger.debug(f"✅ Продавец найден в контейнере: '{text}'")
                        text = text[1:-1]
                        return text
        except Exception as e:
            logger.debug(f"Ошибка поиска в контейнерах: {e}")
        
        logger.warning("⚠️ Продавец не найден ни по одному селектору")
        return None
        
    except Exception as e:
        logger.error(f"Ошибка извлечения продавца: {e}")
        return None

def WB_for(list_links):
    """
    Извлекает информацию о продавцах для списка товаров WB
    """
    global stop_flag
    
    if not driver:
        logger.error("❌ Драйвер не инициализирован")
        return []
        
    n = 0
    sellers = []
    processed = 0
    
    logger.info(f"🔍 Начинаем обработку {len(list_links)} товаров...")
    
    for link in list_links:
        try:
            check_stop_flag()
            
            # Проверяем капчу перед переходом на товар
            if detect_captcha():
                logger.warning("🚨 Капча обнаружена при обработке товара!")
                if not wait_for_captcha_resolution():
                    logger.error("❌ Не удалось решить капчу")
                    sellers.append({
                        "link": link,
                        "seller": "Ошибка капчи"
                    })
                    continue
            
            driver.get(link)
            time.sleep(3)
            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(2)
            scroll_positions = [300, 600, 1000, 1200]
            seller = None
            
            for scroll_pos in scroll_positions:
                driver.execute_script(f"window.scrollTo(0, {scroll_pos});")
                time.sleep(1)
                
                seller = get_seller_from_product_page()
                if seller:
                    break
            
            if seller:
                sellers.append({
                    "link": link,
                    "seller": seller
                })
                processed += 1
                logger.info(f"✅ Продавец найден: '{seller}' ({processed}/{len(list_links)})")
            else:
                sellers.append({
                    "link": link,
                    "seller": "Не найден"
                })
                logger.warning(f"⚠️ Продавец не найден: {link}")

                try:
                    driver.save_screenshot(f"debug_seller_not_found_{n}.png")
                    logger.debug(f"📸 Скриншот сохранен: debug_seller_not_found_{n}.png")
                except:
                    pass
            
            n += 1

            time.sleep(2)
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки товара {link}: {e}")

            if detect_captcha():
                logger.warning("🚨 Капча при обработке товара!")
                if not wait_for_captcha_resolution():
                    sellers.append({
                        "link": link,
                        "seller": "Ошибка капчи"
                    })
                    continue

            sellers.append({
                "link": link,
                "seller": "Ошибка"
            })
            
            n += 1
            continue
    
    logger.info(f"🏁 Обработка завершена! Успешно: {processed}/{len(list_links)}")
    return sellers

def set_stop_flag(value=True):
    """Устанавливает флаг остановки"""
    global stop_flag
    stop_flag = value
    if value:
        logger.info("🛑 Установлен флаг остановки процесса")

def set_captcha_resolved():
    """Функция для вызова извне при решении капчи"""
    global captcha_event
    captcha_event.set()
    logger.info("🔓 Капча помечена как решенная")

def get_captcha_status():
    """Возвращает статус капчи"""
    global captcha_detected
    return captcha_detected

def close_driver():
    """Закрывает драйвер"""
    global driver
    if driver:
        try:
            driver.quit()
            logger.info("🔒 Драйвер закрыт")
        except:
            pass
        driver = None


