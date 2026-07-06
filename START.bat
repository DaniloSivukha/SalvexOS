@echo off
chcp 65001 >nul
title SalvexOS Bootloader
echo ╔══════════════════════════════════════════╗
echo ║     Загрузчик SalvexOS 2026             ║
echo ║     Проверка окружения...               ║
echo ╚══════════════════════════════════════════╝
echo.

:: Проверка наличия Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден!
    echo Установите Python с сайта python.org
    echo И перезапустите этот файл.
    pause
    exit /b 1
)

:: Проверка наличия urwid
python -c "import urwid" >nul 2>&1
if errorlevel 1 (
    echo [ПРЕДУПРЕЖДЕНИЕ] Библиотека urwid не найдена.
    echo Попытка установки...
    pip install urwid
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось установить urwid.
        echo Установите вручную: pip install urwid
        pause
        exit /b 1
    )
)

:: Проверка наличия Pillow (опционально)
python -c "import PIL" >nul 2>&1
if errorlevel 1 (
    echo [ИНФО] Для просмотра изображений установите Pillow:
    echo pip install Pillow
    echo Пропускаем, система запустится без изображений.
)

echo.
echo ╔══════════════════════════════════════════╗
echo ║     Управление версией SalvexOS         ║
echo ╚══════════════════════════════════════════╝
echo.

set URL=https://raw.githubusercontent.com/DaniloSivukha/SalvexOS/refs/heads/main/kernel.py
set LOCAL_FILE=kernel.py

:: Проверяем наличие локального файла
if exist "%LOCAL_FILE%" (
    echo [ИНФО] Локальная версия kernel.py найдена.
    choice /C YN /M "Обновить до последней версии с сервера? (Y/N)"
    if errorlevel 2 goto :run_local
    if errorlevel 1 goto :download
) else (
    echo [ИНФО] Локальная версия не найдена. Загружаем с сервера...
    goto :download
)

:download
echo [ИНФО] Загрузка kernel.py с сервера...
powershell -Command "Invoke-WebRequest -Uri %URL% -OutFile %LOCAL_FILE%"
if errorlevel 1 (
    echo [ОШИБКА] Не удалось загрузить файл.
    echo Проверьте подключение к интернету и повторите.
    pause
    exit /b 1
)
echo [OK] Файл успешно загружен.
goto :run

:run_local
echo [ИНФО] Запуск локальной версии...

:run
echo.
echo [OK] Все зависимости готовы.
echo Запуск SalvexOS...
echo.
python kernel.py

:: Если скрипт завершился с ошибкой
if errorlevel 1 (
    echo.
    echo [ОШИБКА] SalvexOS завершилась с ошибкой.
    echo Проверьте консоль выше для деталей.
    pause
    exit /b 1
)

:: Если всё ок
echo.
echo [OK] SalvexOS завершила работу.
pause