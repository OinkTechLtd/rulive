#!/usr/bin/env python3
"""
LiveM3U - Автоматический поисковой робот для создания актуальных M3U плейлистов
Ищет рабочие прямые ссылки на потоки и обновляет плейлист автоматически
"""

import os
import re
import json
import time
import logging
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Конфигурация
BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

# Создаем директории
for directory in [CONFIG_DIR, DATA_DIR, LOGS_DIR]:
    directory.mkdir(exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGS_DIR / "livem3u.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class StreamInfo:
    """Информация о потоке"""
    name: str
    url: str
    category: str = "Общее"
    country: str = "RU"
    language: str = "rus"
    logo: str = ""
    group_title: str = ""
    last_checked: str = ""
    status: str = "unknown"  # working, dead, unknown

    def to_m3u_line(self) -> str:
        """Преобразовать в формат M3U"""
        logo_attr = f' tvg-logo="{self.logo}"' if self.logo else ""
        group_attr = f' group-title="{self.group_title}"' if self.group_title else ""
        return f'#EXTINF:-1{logo_attr}{group_attr}, {self.name}\n{self.url}'


class StreamChecker:
    """Проверка работоспособности потоков"""
    
    def __init__(self, timeout: int = 5, max_retries: int = 2):
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Connection': 'keep-alive'
        })
    
    def check_stream(self, stream: StreamInfo) -> StreamInfo:
        """Проверить один поток"""
        for attempt in range(self.max_retries):
            try:
                response = self.session.head(
                    stream.url, 
                    timeout=self.timeout,
                    allow_redirects=True
                )
                if response.status_code == 200:
                    stream.status = "working"
                    stream.last_checked = datetime.now().isoformat()
                    logger.info(f"✓ Рабочий поток: {stream.name}")
                    return stream
                elif response.status_code in [403, 404]:
                    stream.status = "dead"
                    stream.last_checked = datetime.now().isoformat()
                    logger.warning(f"✗ Мёртвый поток ({response.status_code}): {stream.name}")
                    return stream
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    stream.status = "dead"
                    stream.last_checked = datetime.now().isoformat()
                    logger.warning(f"✗ Ошибка проверки: {stream.name} - {str(e)}")
                else:
                    time.sleep(1)
        
        stream.last_checked = datetime.now().isoformat()
        return stream


class StreamFinder:
    """Поисковой робот для нахождения потоков"""
    
    def __init__(self):
        self.sources = self._load_sources()
        self.checker = StreamChecker()
    
    def _load_sources(self) -> List[Dict]:
        """Загрузить источники для поиска"""
        sources_file = CONFIG_DIR / "sources.json"
        if sources_file.exists():
            with open(sources_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Источники по умолчанию (только доступные в РФ)
        default_sources = [
            {
                "name": "Первый канал",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/1.m3u8",
                    "https://edge1.1cliptv.com/dash-live2/streams/1ch/1ch.mpd"
                ],
                "category": "Федеральные"
            },
            {
                "name": "Россия 1",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/2.m3u8",
                    "https://player.smotrim.ru/iframe/stream/live_id/2963"
                ],
                "category": "Федеральные"
            },
            {
                "name": "НТВ",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/4.m3u8"
                ],
                "category": "Федеральные"
            },
            {
                "name": "ТНТ",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/5.m3u8"
                ],
                "category": "Развлекательные"
            },
            {
                "name": "РЕН ТВ",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/7.m3u8"
                ],
                "category": "Федеральные"
            },
            {
                "name": "СТС",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/8.m3u8"
                ],
                "category": "Развлекательные"
            },
            {
                "name": "Домашний",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/9.m3u8"
                ],
                "category": "Развлекательные"
            },
            {
                "name": "ТВ-3",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/10.m3u8"
                ],
                "category": "Развлекательные"
            },
            {
                "name": "Пятница!",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/11.m3u8"
                ],
                "category": "Развлекательные"
            },
            {
                "name": "Звезда",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/13.m3u8"
                ],
                "category": "Федеральные"
            },
            {
                "name": "Мир",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/14.m3u8"
                ],
                "category": "Федеральные"
            },
            {
                "name": "ТВ Центр",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/15.m3u8"
                ],
                "category": "Федеральные"
            },
            {
                "name": "РТР-Планета",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/16.m3u8"
                ],
                "category": "Международные"
            },
            {
                "name": "Россия 24",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/17.m3u8",
                    "https://player.smotrim.ru/iframe/stream/live_id/2964"
                ],
                "category": "Новости"
            },
            {
                "name": "Карусель",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/18.m3u8"
                ],
                "category": "Детские"
            },
            {
                "name": "ОТР",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/19.m3u8"
                ],
                "category": "Федеральные"
            },
            {
                "name": "ТВ Культура",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/20.m3u8"
                ],
                "category": "Культура"
            },
            {
                "name": "Матч ТВ",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/21.m3u8"
                ],
                "category": "Спорт"
            },
            {
                "name": "Матч! Страна",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/22.m3u8"
                ],
                "category": "Спорт"
            },
            {
                "name": "Матч! Боец",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/23.m3u8"
                ],
                "category": "Спорт"
            },
            {
                "name": "Матч! Премьер",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/24.m3u8"
                ],
                "category": "Спорт"
            },
            {
                "name": "Кинопоиск",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/25.m3u8"
                ],
                "category": "Кино"
            },
            {
                "name": "ВГТРК",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/26.m3u8"
                ],
                "category": "Региональные"
            },
            {
                "name": "Москва 24",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/27.m3u8"
                ],
                "category": "Региональные"
            },
            {
                "name": "МИР 24",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/28.m3u8"
                ],
                "category": "Новости"
            },
            {
                "name": "Лента.ру",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/29.m3u8"
                ],
                "category": "Новости"
            },
            {
                "name": "Известия",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/30.m3u8"
                ],
                "category": "Новости"
            },
            {
                "name": "Дождь",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/31.m3u8"
                ],
                "category": "Новости"
            },
            {
                "name": "RTД",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/32.m3u8"
                ],
                "category": "Документальные"
            },
            {
                "name": "History",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/33.m3u8"
                ],
                "category": "Документальные"
            },
            {
                "name": "National Geographic",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/34.m3u8"
                ],
                "category": "Документальные"
            },
            {
                "name": "Discovery",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/35.m3u8"
                ],
                "category": "Документальные"
            },
            {
                "name": "Animal Planet",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/36.m3u8"
                ],
                "category": "Документальные"
            },
            {
                "name": "Euronews",
                "urls": [
                    "https://streaming.televizor-24.ru/channels/37.m3u8"
                ],
                "category": "Новости"
            }
        ]
        
        # Сохраняем источники по умолчанию
        with open(sources_file, 'w', encoding='utf-8') as f:
            json.dump(default_sources, f, ensure_ascii=False, indent=2)
        
        return default_sources
    
    def find_streams(self) -> List[StreamInfo]:
        """Найти все потоки из источников"""
        streams = []
        logger.info("Начинаю поиск потоков...")
        
        for source in self.sources:
            for url in source["urls"]:
                stream = StreamInfo(
                    name=source["name"],
                    url=url,
                    category=source.get("category", "Общее"),
                    country="RU",
                    language="rus",
                    group_title=source.get("category", "Общее")
                )
                streams.append(stream)
        
        logger.info(f"Найдено {len(streams)} потенциальных потоков")
        return streams
    
    def check_all_streams(self, streams: List[StreamInfo], max_workers: int = 10) -> List[StreamInfo]:
        """Проверить все потоки параллельно"""
        logger.info(f"Проверяю потоки ({max_workers} потоков)...")
        checked_streams = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.checker.check_stream, stream): stream for stream in streams}
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    checked_streams.append(result)
                except Exception as e:
                    logger.error(f"Ошибка при проверке потока: {e}")
        
        working_count = sum(1 for s in checked_streams if s.status == "working")
        logger.info(f"Проверка завершена. Рабочих: {working_count}/{len(checked_streams)}")
        return checked_streams


class M3UPlaylist:
    """Генератор M3U плейлистов"""
    
    def __init__(self, output_dir: Path = DATA_DIR):
        self.output_dir = output_dir
    
    def generate_m3u(self, streams: List[StreamInfo], filename: str = "playlist.m3u") -> Path:
        """Сгенерировать M3U файл"""
        output_path = self.output_dir / filename
        
        # Фильтруем только рабочие потоки
        working_streams = [s for s in streams if s.status == "working"]
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            f.write(f"# Обновлён: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Всего каналов: {len(working_streams)}\n")
            f.write(f"# LiveM3U - Автоматический генератор плейлистов\n\n")
            
            # Сортируем по категориям
            categories = {}
            for stream in working_streams:
                if stream.category not in categories:
                    categories[stream.category] = []
                categories[stream.category].append(stream)
            
            for category in sorted(categories.keys()):
                f.write(f"\n# {category}\n")
                for stream in categories[category]:
                    f.write(stream.to_m3u_line() + "\n")
        
        logger.info(f"Плейлист сохранён: {output_path} ({len(working_streams)} каналов)")
        return output_path
    
    def generate_m3u8(self, streams: List[StreamInfo], filename: str = "playlist.m3u8") -> Path:
        """Сгенерировать M3U8 файл (для HLS)"""
        return self.generate_m3u(streams, filename)
    
    def save_statistics(self, streams: List[StreamInfo]) -> Path:
        """Сохранить статистику"""
        stats_path = self.output_dir / "statistics.json"
        
        stats = {
            "generated_at": datetime.now().isoformat(),
            "total_streams": len(streams),
            "working_streams": sum(1 for s in streams if s.status == "working"),
            "dead_streams": sum(1 for s in streams if s.status == "dead"),
            "unknown_streams": sum(1 for s in streams if s.status == "unknown"),
            "categories": {}
        }
        
        # Статистика по категориям
        for stream in streams:
            if stream.category not in stats["categories"]:
                stats["categories"][stream.category] = {"total": 0, "working": 0}
            stats["categories"][stream.category]["total"] += 1
            if stream.status == "working":
                stats["categories"][stream.category]["working"] += 1
        
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Статистика сохранена: {stats_path}")
        return stats_path


class LiveM3UBot:
    """Основной класс бота"""
    
    def __init__(self, check_interval: int = 3600):
        """
        Инициализация бота
        :param check_interval: Интервал проверки в секундах (по умолчанию 1 час)
        """
        self.finder = StreamFinder()
        self.playlist = M3UPlaylist()
        self.check_interval = check_interval
        self.running = False
    
    def run_once(self) -> Tuple[int, int]:
        """Выполнить одну итерацию поиска и обновления"""
        logger.info("=" * 50)
        logger.info("Запуск LiveM3U Bot")
        logger.info("=" * 50)
        
        # Поиск потоков
        streams = self.finder.find_streams()
        
        # Проверка потоков
        checked_streams = self.finder.check_all_streams(streams)
        
        # Генерация плейлиста
        self.playlist.generate_m3u(checked_streams)
        self.playlist.generate_m3u8(checked_streams)
        
        # Сохранение статистики
        self.playlist.save_statistics(checked_streams)
        
        working = sum(1 for s in checked_streams if s.status == "working")
        total = len(checked_streams)
        
        logger.info("=" * 50)
        logger.info(f"Готово! Рабочих каналов: {working}/{total}")
        logger.info("=" * 50)
        
        return working, total
    
    def run_continuous(self):
        """Запустить в непрерывном режиме"""
        self.running = True
        logger.info(f"Запуск в непрерывном режиме (интервал: {self.check_interval}с)")
        
        while self.running:
            try:
                self.run_once()
                logger.info(f"Следующая проверка через {self.check_interval} секунд...")
                time.sleep(self.check_interval)
            except KeyboardInterrupt:
                logger.info("Остановка по запросу пользователя")
                self.stop()
            except Exception as e:
                logger.error(f"Ошибка в основном цикле: {e}")
                time.sleep(60)  # Ждём минуту перед повторной попыткой
    
    def stop(self):
        """Остановить бота"""
        self.running = False
        logger.info("Бот остановлен")


def main():
    """Точка входа"""
    import argparse
    
    parser = argparse.ArgumentParser(description="LiveM3U - Автоматический генератор IPTV плейлистов")
    parser.add_argument("--once", action="store_true", help="Выполнить один раз и выйти")
    parser.add_argument("--interval", type=int, default=3600, help="Интервал проверки в секундах (по умолчанию 3600)")
    parser.add_argument("--workers", type=int, default=10, help="Количество потоков для проверки (по умолчанию 10)")
    
    args = parser.parse_args()
    
    bot = LiveM3UBot(check_interval=args.interval)
    
    if args.once:
        bot.run_once()
    else:
        bot.run_continuous()


if __name__ == "__main__":
    main()
