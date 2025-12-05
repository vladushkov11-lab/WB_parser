import threading
import time
from flask import Flask, render_template, request, jsonify
from wb_api import collect_products_until_upsell, WB_for, detect_captcha, wait_for_captcha_resolution, set_captcha_resolved, get_captcha_status, set_stop_flag, close_driver
from spreadsheets import google_add
import logging

app = Flask(__name__)

# Глобальные переменные для управления процессом
current_thread = None
stop_process = False
process_status = {
    "running": False,
    "current_step": "Готов к запуску",
    "progress": 0,
    "found_products": 0,
    "processed_sellers": 0,
    "captcha_detected": False
}

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_wb_scraping(brand="Dazle"):
    """Запускает процесс парсинга Wildberries"""
    global stop_process, process_status, current_thread
    
    try:
        process_status["running"] = True
        process_status["current_step"] = "Начинаем сбор товаров с Wildberries..."
        process_status["progress"] = 5
        process_status["captcha_detected"] = False
        
        # Сбор товаров
        if stop_process:
            return
        
        logger.info(f"🔍 Начинаем сбор товаров для бренда: {brand}")
        list_links = collect_products_until_upsell(brand=brand, max_products=100, max_scroll_steps=20, scroll_pause=1)
        process_status["found_products"] = len(list_links)
        process_status["current_step"] = f"Найдено {len(list_links)} товаров. Получаем информацию о продавцах..."
        process_status["progress"] = 40
        
        if stop_process:
            return
        
        # Получение информации о продавцах
        logger.info(f"🏪 Получаем информацию о продавцах для {len(list_links)} товаров...")
        list_sellers = WB_for(list_links)
        process_status["processed_sellers"] = len([s for s in list_sellers if s['seller'] != "Не найден" and s['seller'] != "Ошибка"])
        process_status["current_step"] = "Сохраняем результаты в Google Sheets..."
        process_status["progress"] = 75
        
        if stop_process:
            return
        print(list_sellers)
        # Сохранение в Google Sheets
        logger.info("💾 Сохраняем результаты в Google Sheets...")
        google_add(sellers_data=list_sellers, target_brand=brand)
        
        process_status["current_step"] = "Процесс завершен успешно!"
        process_status["progress"] = 100
        
        logger.info(f"✅ Парсинг завершен! Обработано: {process_status['processed_sellers']} товаров")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в процессе парсинга: {e}")
        process_status["current_step"] = f"Ошибка: {str(e)[:100]}..."
        process_status["progress"] = 0
    finally:
        process_status["running"] = False
        current_thread = None

@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>WB Parser - Парсер товаров Wildberries</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 900px;
                margin: 0 auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }
            h1 {
                color: #333;
                text-align: center;
                margin-bottom: 30px;
                font-size: 2.2em;
                background: linear-gradient(45deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            .subtitle {
                text-align: center;
                color: #666;
                margin-bottom: 40px;
                font-size: 1.1em;
            }
            .form-group {
                margin-bottom: 25px;
            }
            label {
                display: block;
                margin-bottom: 8px;
                font-weight: 600;
                color: #555;
                font-size: 1.1em;
            }
            input[type="text"] {
                width: 100%;
                padding: 15px;
                border: 2px solid #e1e5e9;
                border-radius: 10px;
                font-size: 16px;
                box-sizing: border-box;
                transition: border-color 0.3s;
            }
            input[type="text"]:focus {
                border-color: #667eea;
                outline: none;
                box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
            }
            .btn {
                padding: 15px 30px;
                margin: 10px 5px;
                border: none;
                border-radius: 10px;
                cursor: pointer;
                font-size: 16px;
                font-weight: 600;
                transition: all 0.3s;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            }
            .btn-start {
                background: linear-gradient(45deg, #4CAF50, #45a049);
                color: white;
            }
            .btn-start:hover:not(:disabled) {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(76, 175, 80, 0.4);
            }
            .btn-start:disabled {
                background: #cccccc;
                cursor: not-allowed;
                box-shadow: none;
            }
            .btn-stop {
                background: linear-gradient(45deg, #f44336, #da190b);
                color: white;
            }
            .btn-stop:hover:not(:disabled) {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(244, 67, 54, 0.4);
            }
            .btn-stop:disabled {
                background: #cccccc;
                cursor: not-allowed;
                box-shadow: none;
            }
            .btn-captcha {
                background: linear-gradient(45deg, #ff9800, #f57c00);
                color: white;
                display: none;
            }
            .btn-captcha:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(255, 152, 0, 0.4);
            }
            .captcha-alert {
                margin: 25px 0;
                padding: 20px;
                border-radius: 10px;
                background: linear-gradient(45deg, #fff3cd, #ffeaa7);
                border: 2px solid #ff9800;
                border-left: 6px solid #ff9800;
                display: none;
                box-shadow: 0 4px 15px rgba(255, 152, 0, 0.2);
            }
            .captcha-alert.show {
                display: block;
                animation: slideIn 0.3s ease-out;
            }
            @keyframes slideIn {
                from { opacity: 0; transform: translateY(-20px); }
                to { opacity: 1; transform: translateY(0); }
            }
            .warning-icon {
                color: #ff9800;
                font-size: 20px;
                margin-right: 10px;
            }
            .status {
                margin: 25px 0;
                padding: 20px;
                border-radius: 10px;
                background: linear-gradient(45deg, #e8f5e8, #d4edda);
                border-left: 6px solid #4CAF50;
                box-shadow: 0 4px 15px rgba(76, 175, 80, 0.2);
            }
            .status.error {
                background: linear-gradient(45deg, #ffe8e8, #f8d7da);
                border-left-color: #f44336;
            }
            .progress-container {
                margin: 30px 0;
                background: #f8f9fa;
                border-radius: 10px;
                padding: 20px;
                box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);
            }
            .progress-label {
                text-align: center;
                margin-bottom: 10px;
                font-weight: 600;
                color: #555;
            }
            .progress-bar {
                width: 100%;
                height: 25px;
                background-color: #e9ecef;
                border-radius: 15px;
                overflow: hidden;
                box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);
            }
            .progress-fill {
                height: 100%;
                background: linear-gradient(45deg, #667eea, #764ba2);
                transition: width 0.5s ease;
                border-radius: 15px;
                position: relative;
            }
            .progress-fill::after {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
                animation: shimmer 2s infinite;
            }
            @keyframes shimmer {
                0% { transform: translateX(-100%); }
                100% { transform: translateX(100%); }
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-top: 30px;
            }
            .stat-card {
                background: linear-gradient(135deg, #f8f9fa, #e9ecef);
                padding: 25px;
                border-radius: 15px;
                text-align: center;
                border: 2px solid #dee2e6;
                transition: transform 0.3s;
            }
            .stat-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 8px 25px rgba(0,0,0,0.15);
            }
            .stat-number {
                font-size: 2.5em;
                font-weight: bold;
                background: linear-gradient(45deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                margin-bottom: 5px;
            }
            .stat-label {
                color: #666;
                font-weight: 600;
                font-size: 1.1em;
            }
            .wb-logo {
                text-align: center;
                font-size: 3em;
                margin-bottom: 20px;
            }
            .features {
                background: #f8f9fa;
                padding: 20px;
                border-radius: 10px;
                margin-top: 30px;
            }
            .features h3 {
                color: #333;
                margin-bottom: 15px;
            }
            .features ul {
                list-style: none;
                padding: 0;
            }
            .features li {
                padding: 8px 0;
                border-bottom: 1px solid #dee2e6;
            }
            .features li:last-child {
                border-bottom: none;
            }
            .features li::before {
                content: "✅";
                margin-right: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="wb-logo">🛒</div>
            <h1>WB Parser</h1>
            <p class="subtitle">Профессиональный парсер товаров Wildberries с автоматическим сбором информации о продавцах</p>
            
            <div class="form-group">
                <label for="brand">🎯 Бренд для поиска:</label>
                <input type="text" id="brand" value="Dazle" placeholder="Введите название бренда (например: Dazle, Nike, Adidas)">
            </div>
            
            <div class="form-group" style="text-align: center;">
                <button id="startBtn" class="btn btn-start" onclick="startProcess()">🚀 Начать парсинг</button>
                <button id="stopBtn" class="btn btn-stop" onclick="stopProcess()" disabled>⏹️ Остановить</button>
                <button id="captchaBtn" class="btn btn-captcha" onclick="resolveCaptcha()">✅ Капча решена</button>
            </div>
            
            <div id="captchaAlert" class="captcha-alert">
                <span class="warning-icon">⚠️</span>
                <strong>Обнаружена капча!</strong><br>
                Пожалуйста, решите капчу в браузере и нажмите кнопку "Капча решена" когда закончите.
                <br><small>⏰ Максимальное время ожидания: 10 минут</small>
            </div>
            
            <div class="progress-container">
                <div class="progress-label" id="progressLabel">Готов к запуску</div>
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill" style="width: 0%;"></div>
                </div>
            </div>
            
            <div id="status" class="status">
                <div id="statusText">Нажмите "Начать парсинг" для запуска процесса</div>
            </div>
            
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-number" id="foundProducts">0</div>
                    <div class="stat-label">📦 Найдено товаров</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="processedSellers">0</div>
                    <div class="stat-label">🏪 Обработано продавцов</div>
                </div>
            </div>

        </div>

        <script>
            let statusInterval;

            function updateStatus() {
                fetch('/status')
                    .then(response => response.json())
                    .then(data => {
                        // Обновляем прогресс
                        document.getElementById('progressFill').style.width = data.progress + '%';
                        document.getElementById('progressLabel').textContent = data.current_step;
                        document.getElementById('statusText').textContent = data.current_step;
                        
                        // Обновляем статистику
                        document.getElementById('foundProducts').textContent = data.found_products;
                        document.getElementById('processedSellers').textContent = data.processed_sellers;
                        
                        // Обновляем статус выполнения
                        const statusDiv = document.getElementById('status');
                        if (data.current_step.includes('Ошибка') || data.current_step.includes('ошибка')) {
                            statusDiv.className = 'status error';
                        } else if (data.running) {
                            statusDiv.className = 'status';
                        } else {
                            statusDiv.className = 'status';
                        }
                        
                        // Управление кнопками
                        const startBtn = document.getElementById('startBtn');
                        const stopBtn = document.getElementById('stopBtn');
                        
                        startBtn.disabled = data.running;
                        stopBtn.disabled = !data.running;
                        
                        // Показываем/скрываем кнопку капчи и алерт
                        const captchaAlert = document.getElementById('captchaAlert');
                        const captchaBtn = document.getElementById('captchaBtn');
                        
                        if (data.captcha_detected) {
                            captchaAlert.classList.add('show');
                            captchaBtn.style.display = 'inline-block';
                        } else {
                            captchaAlert.classList.remove('show');
                            captchaBtn.style.display = 'none';
                        }
                        
                        // Останавливаем обновление если процесс завершен
                        if (!data.running && statusInterval) {
                            clearInterval(statusInterval);
                            statusInterval = null;
                            
                            // Если процесс завершен успешно, показываем сообщение
                            if (data.progress === 100 && !data.current_step.includes('Ошибка')) {
                                setTimeout(() => {
                                    document.getElementById('progressLabel').textContent = '✅ Парсинг завершен успешно!';
                                }, 500);
                            }
                        }
                    })
                    .catch(error => {
                        console.error('Ошибка получения статуса:', error);
                        document.getElementById('statusText').textContent = 'Ошибка связи с сервером';
                    });
            }

            function startProcess() {
                const brand = document.getElementById('brand').value.trim();
                
                if (!brand) {
                    alert('Пожалуйста, введите название бренда');
                    return;
                }
                
                fetch('/start', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({brand: brand})
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        // Сбрасываем статистику
                        document.getElementById('foundProducts').textContent = '0';
                        document.getElementById('processedSellers').textContent = '0';
                        document.getElementById('progressFill').style.width = '0%';
                        
                        // Запускаем обновление статуса
                        statusInterval = setInterval(updateStatus, 1000);
                        updateStatus();
                        
                        document.getElementById('progressLabel').textContent = '🚀 Запуск парсинга...';
                    } else {
                        alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
                    }
                })
                .catch(error => {
                    console.error('Ошибка:', error);
                    alert('Ошибка запуска процесса');
                });
            }

            function stopProcess() {
                if (confirm('Вы уверены, что хотите остановить процесс парсинга?')) {
                    fetch('/stop', {method: 'POST'})
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                console.log('Процесс остановлен');
                                document.getElementById('progressLabel').textContent = '⏹️ Процесс остановлен пользователем';
                            }
                        })
                        .catch(error => {
                            console.error('Ошибка остановки:', error);
                        });
                }
            }
            
            function resolveCaptcha() {
                fetch('/captcha-resolved', {method: 'POST'})
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            console.log('Капча помечена как решенная');
                            document.getElementById('progressLabel').textContent = '✅ Капча решена, продолжаем...';
                        }
                    })
                    .catch(error => {
                        console.error('Ошибка:', error);
                    });
            }

            // Обновляем статус при загрузке страницы
            updateStatus();
            
            // Добавляем обработку Enter в поле ввода
            document.getElementById('brand').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    startProcess();
                }
            });
        </script>
    </body>
    </html>
    '''

@app.route('/start', methods=['POST'])
def start_scraping():
    """Запускает процесс парсинга"""
    global current_thread, stop_process, process_status
    
    if process_status["running"]:
        return jsonify({"success": False, "error": "Процесс парсинга уже выполняется"})
    
    data = request.get_json()
    brand = data.get('brand', 'Dazle')
    
    # Сброс флага остановки
    stop_process = False
    
    # Сброс статуса
    process_status = {
        "running": True,
        "current_step": "Инициализация...",
        "progress": 0,
        "found_products": 0,
        "processed_sellers": 0,
        "captcha_detected": False
    }
    
    # Запуск в отдельном потоке
    current_thread = threading.Thread(target=run_wb_scraping, args=(brand,))
    current_thread.daemon = True
    current_thread.start()
    
    return jsonify({"success": True})

@app.route('/stop', methods=['POST'])
def stop_scraping():
    """Останавливает процесс парсинга"""
    global stop_process
    
    stop_process = True
    set_stop_flag(True)  # Останавливаем парсер
    return jsonify({"success": True})

@app.route('/captcha-resolved', methods=['POST'])
def captcha_resolved():
    """Отмечает капчу как решенную"""
    try:
        set_captcha_resolved()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/status')
def get_status():
    """Возвращает текущий статус процесса"""
    # Обновляем статус капчи
    process_status["captcha_detected"] = get_captcha_status()
    return jsonify(process_status)

@app.route('/health')
def health_check():
    """Проверка состояния сервера"""
    return jsonify({"status": "ok", "service": "WB Parser"})

if __name__ == '__main__':
    logger.info("🚀 Запуск WB Parser Web Application...")
    logger.info("📱 Откройте в браузере: http://localhost:5000")
    logger.info("⚡ Максимальная производительность и стабильность!")
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)