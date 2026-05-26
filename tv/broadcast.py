#!/usr/bin/env python3
import os
import http.server
import socketserver
import threading
import time
import subprocess
import signal
import sys

# Конфигурация
PORT = 8080
DIRECTORY = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PLAYLIST = "live_stream.m3u8"
SEGMENT_DURATION = 4  # Длительность сегмента в секундах
LOGO_TEXT = "LiveM3U Инфо"

# Файлы для вещания (порядок важен)
MEDIA_FILES = [
    "infokanal.ts",
    "moscow878.ts"
]

def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def log_message(self, format, *args):
        # Подавляем стандартные логи HTTP сервера для чистоты вывода
        pass

def generate_playlist():
    """Генерирует статический m3u8 плейлист для скачивания/просмотра файлов"""
    playlist_content = "#EXTM3U\n"
    playlist_content += "#EXT-X-VERSION:3\n"
    playlist_content += "#EXT-X-TARGETDURATION:10\n"
    playlist_content += "#EXT-X-MEDIA-SEQUENCE:0\n"
    playlist_content += "#EXT-X-PLAYLIST-TYPE:VOD\n" # Или EVENT, если бы было живое
    
    for file in MEDIA_FILES:
        if os.path.exists(os.path.join(DIRECTORY, file)):
            # Используем относительный путь или localhost для локального просмотра
            playlist_content += f"#EXTINF:10.0,\n{file}\n"
            
    playlist_content += "#EXT-X-ENDLIST\n"
    
    with open("catalog.m3u8", "w") as f:
        f.write(playlist_content)
    print(f"[INFO] Создан каталог файлов: catalog.m3u8")

def start_broadcast():
    """Запускает FFmpeg для создания HLS потока с логотипом"""
    if not check_ffmpeg():
        print("[ОШИБКА] FFmpeg не найден! Установите FFmpeg для работы вещания.")
        return

    # Создаем список файлов для конкатенации
    file_list_path = os.path.join(DIRECTORY, "file_list.txt")
    with open(file_list_path, "w") as f:
        for media_file in MEDIA_FILES:
            full_path = os.path.join(DIRECTORY, media_file)
            if os.path.exists(full_path):
                f.write(f"file '{media_file}'\n")
            else:
                print(f"[ПРЕДУПРЕЖДЕНИЕ] Файл {media_file} не найден и будет пропущен.")

    if not os.path.exists(file_list_path) or os.path.getsize(file_list_path) == 0:
        print("[ОШИБКА] Нет доступных файлов для вещания.")
        return

    # Команда FFmpeg
    # -re: читать с нативной скоростью (эмуляция эфира)
    # -stream_loop -1: бесконечный цикл
    # -vf drawtext: наложение текста (логотипа)
    # Используем простой фильтр для логотипа без border (не поддерживается в этой версии)
    cmd = [
        "ffmpeg",
        "-re",
        "-stream_loop", "-1",
        "-f", "concat",
        "-safe", "0",
        "-i", file_list_path,
        "-c:v", "libx264",
        "-preset", "fast",
        "-g", "48",
        "-c:a", "aac",
        "-b:a", "128k",
        "-vf", f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='{LOGO_TEXT}':x=10:y=10:fontsize=24:fontcolor=white@0.9:shadowcolor=black:shadowx=2:shadowy=2",
        "-f", "hls",
        "-hls_time", str(SEGMENT_DURATION),
        "-hls_list_size", "0",
        "-hls_segment_filename", "segment_%03d.ts",
        OUTPUT_PLAYLIST
    ]
    
    # Попытка запустить с шрифтом, если шрифта нет, пробуем без него или с дефолтным
    try:
        print(f"[INFO] Запуск вещания канала 'LiveM3U Инфо' на порту {PORT}...")
        print(f"[INFO] Плейлист доступен по адресу: http://localhost:{PORT}/{OUTPUT_PLAYLIST}")
        print(f"[INFO] Для остановки нажмите Ctrl+C")
        
        # Запускаем процесс
        process = subprocess.Popen(cmd, cwd=DIRECTORY)
        return process
    except Exception as e:
        print(f"[ОШИБКА] Не удалось запустить FFmpeg: {e}")
        return None

def run_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"[INFO] HTTP сервер запущен на порту {PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    # Генерируем каталог исходников
    generate_playlist()

    if not check_ffmpeg():
        print("\n=== ВНИМАНИЕ ===")
        print("FFmpeg не установлен. Вещание с логотипом невозможно.")
        print("Вы можете просто открыть catalog.m3u8 в плеере, чтобы посмотреть файлы по очереди.")
        print("Для установки FFmpeg: sudo apt-get install ffmpeg")
        sys.exit(1)

    # Запуск вещания в отдельном потоке (или процессе)
    broadcast_process = start_broadcast()
    
    if broadcast_process:
        try:
            # Запуск HTTP сервера в главном потоке
            run_server()
        except KeyboardInterrupt:
            print("\n[INFO] Остановка сервера...")
            broadcast_process.terminate()
            broadcast_process.wait()
    else:
        print("[ОШИБКА] Не удалось запустить процесс вещания.")
