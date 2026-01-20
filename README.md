# Pills Reminder Bot

Telegram бот для напоминания о приёме таблеток. Работает в групповых чатах, каждый участник видит только свои таблетки.

## Возможности

- Добавление таблеток с названием, дозировкой и фото
- Настройка расписания приёма
- Напоминания в заданное время
- Вечерние напоминания о пропущенных таблетках
- Изоляция данных между пользователями в групповом чате

## Команды

- `/start` - регистрация в боте
- `/help` - справка
- `/addpill` - добавить таблетку
- `/mypills` - список моих таблеток
- `/deletepill` - удалить таблетку
- `/schedule` - управление расписанием
- `/today` - что нужно выпить сегодня

## Установка

### 1. Клонировать репозиторий

```bash
git clone https://github.com/YOUR_USERNAME/Pills_bot.git
cd Pills_bot
```

### 2. Создать виртуальное окружение

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows
```

### 3. Установить зависимости

```bash
pip install -r requirements.txt
```

### 4. Настроить переменные окружения

```bash
cp .env.example .env
```

Отредактируйте `.env` и добавьте свой токен бота:

```
BOT_TOKEN=your_bot_token_here
TIMEZONE=Europe/Moscow
EVENING_REMINDER_TIME=20:00
```

Токен можно получить у [@BotFather](https://t.me/BotFather) в Telegram.

### 5. Запустить бота

```bash
python bot.py
```

## Деплой на Google Cloud VM

### 1. Подключиться к VM

```bash
gcloud compute ssh YOUR_VM_NAME
```

### 2. Установить Python и pip

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv -y
```

### 3. Клонировать и настроить

```bash
git clone https://github.com/YOUR_USERNAME/Pills_bot.git
cd Pills_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env  # добавить токен
```

### 4. Создать systemd сервис

```bash
sudo nano /etc/systemd/system/pills-bot.service
```

Содержимое:

```ini
[Unit]
Description=Pills Reminder Telegram Bot
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/Pills_bot
Environment=PATH=/home/YOUR_USERNAME/Pills_bot/venv/bin
ExecStart=/home/YOUR_USERNAME/Pills_bot/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 5. Запустить сервис

```bash
sudo systemctl daemon-reload
sudo systemctl enable pills-bot
sudo systemctl start pills-bot
```

### 6. Проверить статус

```bash
sudo systemctl status pills-bot
sudo journalctl -u pills-bot -f  # логи
```

## Лицензия

MIT
