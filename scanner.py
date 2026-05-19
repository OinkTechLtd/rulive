import asyncio
import aiohttp
import re
import json
import os
import random
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin
from typing import List, Dict, Set

# ================= КОНФИГУРАЦИЯ =================
PROXY_HOST = os.getenv("PROXY_HOST", "secure-272717.tatnet.app")
PROXY_PORT = os.getenv("PROXY_PORT", "8080")
PROXY_URL = f"http://{PROXY_HOST}:{PROXY_PORT}"

# Настройки проверки
TIMEOUT_SECONDS = 8
MAX_CONCURRENT_CHECKS = 15  # Сколько каналов проверять одновременно
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "VLC/3.0.16 LibVLC/3.0.16"
]

# Пути к файлам
DATA_DIR = "data"
PLAYLIST_FILE = os.path.join(DATA_DIR, "playlist.m3u")
HISTORY_FILE = os.path.join(DATA_DIR, "channel_history.json")
CATEGORIES_DIR = os.path.join(DATA_DIR, "playlists")

# Источники для поиска (GitHub репо, известные листы)
SEARCH_SOURCES = [
    # GitHub IPTV Org (основной источник)
    "https://raw.githubusercontent.com/iptv-org/iptv/master/countries/ru.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/countries/by.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/countries/kz.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/countries/ua.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/categories/news.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/categories/movies.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/categories/sports.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/categories/music.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/categories/kids.m3u",
    # Дополнительные публичные листы
    "https://raw.githubusercontent.com/free-TV/IPTV/master/playlist.m3u8",
    "https://raw.githubusercontent.com/purcell/redsocks/master/iptables.sh", # Иногда содержат ссылки в коментах
]

# Ключевые слова для категоризации
CATEGORIES_MAP = {
    "news": ["новости", "news", "vesti", "24", "info", "мир", "россия"],
    "movies": ["кино", "movie", "film", "hd", "serial", "сериал", "премьера"],
    "sports": ["спорт", "sport", "football", "hockey", "match", "боец"],
    "kids": ["детский", "kids", "cartoon", "disney", "nickelodeon", "мультик"],
    "music": ["музыка", "music", "hit", "radio", "club", "dance"],
    "auto": ["авто", "auto", "drive"],
    "science": ["наука", "science", "doc", "discovery"],
}

class IPTVScanner:
    def __init__(self):
        self.proxy = PROXY_URL
        self.valid_channels: List[Dict] = []
        self.seen_urls: Set[str] = set()
        self.history = self.load_history()
        self.stats = {"total_found": 0, "valid": 0, "dead": 0, "duplicates": 0}
        
    def load_history(self) -> Dict:
        """Загружает историю рабочих каналов, чтобы не проверять их каждый раз."""
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Очищаем старую историю (> 7 дней)
                    cutoff = datetime.now().timestamp() - (7 * 24 * 3600)
                    return {k: v for k, v in data.items() if v > cutoff}
            except:
                pass
        return {}

    def save_history(self):
        """Сохраняет историю успешных проверок."""
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

    async def fetch_url(self, session: aiohttp.ClientSession, url: str) -> str:
        """Скачивает содержимое URL через прокси."""
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        try:
            # Для сырых файлов GitHub прокси может не понадобиться, но для безопасности оставим
            # Если прокси падает, можно попробовать без него для githubusercontent
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15), headers=headers) as response:
                if response.status == 200:
                    return await response.text()
        except Exception as e:
            print(f"⚠️ Ошибка загрузки {url}: {e}")
        return ""

    def parse_m3u_content(self, content: str, source_url: str) -> List[Dict]:
        """Парсит M3U контент и извлекает каналы."""
        channels = []
        lines = content.splitlines()
        current_name = "Unknown Channel"
        current_group = "General"
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith("#EXTINF:"):
                # Извлекаем имя канала
                name_match = re.search(r'tvg-name="([^"]+)"|,(.+)$', line)
                if name_match:
                    current_name = name_match.group(1) or name_match.group(2)
                    current_name = current_name.strip().replace('"', '')
                
                # Извлекаем группу
                group_match = re.search(r'group-title="([^"]+)"', line)
                if group_match:
                    current_group = group_match.group(1)
                    
            elif line.startswith("http"):
                if line not in self.seen_urls:
                    self.seen_urls.add(line)
                    self.stats["total_found"] += 1
                    channels.append({
                        "name": current_name,
                        "url": line,
                        "group": current_group,
                        "source": source_url
                    })
                else:
                    self.stats["duplicates"] += 1
        
        return channels

    async def check_channel_stream(self, session: aiohttp.ClientSession, channel: Dict) -> bool:
        """Проверяет, работает ли ссылка на поток реально."""
        url = channel["url"]
        
        # Если недавно проверяли и работало - пропускаем глубокую проверку
        if url in self.history:
            return True

        try:
            # Делаем HEAD запрос или GET с ограничением, чтобы не качать весь поток
            async with session.head(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS), allow_redirects=True) as response:
                if response.status == 200:
                    content_type = response.headers.get('Content-Type', '').lower()
                    # Проверяем, что это видео или плейлист, а не HTML ошибка
                    if 'text/html' in content_type and 'video' not in content_type:
                        # Дополнительная проверка: иногда сервер отдает 200 на HTML страницу ошибки
                        return False
                    return True
                elif response.status == 403:
                    # 403 часто бывает у работающих потоков (защита от хотлинка), считаем рабочим если есть Content-Length
                    if response.headers.get('Content-Length'):
                        return True
                    return False
        except asyncio.TimeoutError:
            return False
        except Exception:
            return False
        
        # Если HEAD не сработал, пробуем GET первых байт
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS), range=(0, 1024)) as response:
                if response.status in [200, 206]:
                    return True
        except:
            pass
            
        return False

    def categorize_channel(self, name: str, group: str) -> str:
        """Определяет категорию канала."""
        text = (name + " " + group).lower()
        for cat, keywords in CATEGORIES_MAP.items():
            if any(k in text for k in keywords):
                return cat
        return "general"

    async def run(self):
        print(f"🚀 ЗАПУСК СКАНЕРА ЧЕРЕЗ ПРОКСИ: {self.proxy}")
        print("🌐 Поиск источников и парсинг...")

        connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_CHECKS)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            all_raw_channels = []

            # 1. Сбор каналов из известных источников
            tasks = [self.fetch_url(session, url) for url in SEARCH_SOURCES]
            results = await asyncio.gather(*tasks)

            for i, content in enumerate(results):
                if content:
                    found = self.parse_m3u_content(content, SEARCH_SOURCES[i])
                    all_raw_channels.extend(found)
                    print(f"✅ Обработан источник: {SEARCH_SOURCES[i]} (найдено: {len(found)})")

            print(f"\n📊 Всего найдено уникальных ссылок: {len(all_raw_channels)}")
            print("🔍 Начинаем проверку работоспособности потоков (это может занять время)...")

            # 2. Проверка работоспособности
            valid_channels = []
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)

            async def safe_check(ch):
                async with semaphore:
                    is_valid = await self.check_channel_stream(session, ch)
                    if is_valid:
                        self.history[ch["url"]] = datetime.now().timestamp()
                        return ch
                    return None

            # Обрабатываем батчами, чтобы видеть прогресс
            batch_size = 50
            total_batches = (len(all_raw_channels) + batch_size - 1) // batch_size

            for i in range(0, len(all_raw_channels), batch_size):
                batch = all_raw_channels[i:i+batch_size]
                tasks = [safe_check(ch) for ch in batch]
                results = await asyncio.gather(*tasks)
                
                for ch in results:
                    if ch:
                        valid_channels.append(ch)
                
                current_progress = min(i + batch_size, len(all_raw_channels))
                print(f"⏳ Прогресс: {current_progress}/{len(all_raw_channels)} | Рабочих найдено: {len(valid_channels)}")

            self.valid_channels = valid_channels
            print(f"\n🎉 ПРОВЕРКА ЗАВЕРШЕНА! Рабочих каналов: {len(valid_channels)}")
            
            # 3. Сохранение результатов
            self.save_results()

    def save_results(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(CATEGORIES_DIR, exist_ok=True)

        # Сортировка по имени
        self.valid_channels.sort(key=lambda x: x["name"])

        # 1. Полный плейлист
        with open(PLAYLIST_FILE, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n# Generated by Auto-Scanner with Proxy secure-272717.tatnet.app\n")
            f.write(f"# Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Total Channels: {len(self.valid_channels)}\n\n")
            
            for ch in self.valid_channels:
                f.write(f'#EXTINF:-1 tvg-name="{ch["name"]}" group-title="{ch["group"]}",{ch["name"]}\n')
                f.write(f'{ch["url"]}\n')
        
        print(f"💾 Сохранен полный плейлист: {PLAYLIST_FILE}")

        # 2. Тематические плейлисты
        categorized = {cat: [] for cat in list(CATEGORIES_MAP.keys()) + ["general"]}
        
        for ch in self.valid_channels:
            cat = self.categorize_channel(ch["name"], ch["group"])
            categorized[cat].append(ch)

        for cat, channels in categorized.items():
            if not channels:
                continue
            filename = os.path.join(CATEGORIES_DIR, f"{cat}.m3u")
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"#EXTM3U\n# Category: {cat.upper()}\n\n")
                for ch in channels:
                    f.write(f'#EXTINF:-1 tvg-name="{ch["name"]}",{ch["name"]}\n')
                    f.write(f'{ch["url"]}\n')
            print(f"📂 Категория '{cat}': {len(channels)} каналов")

        # 3. История
        self.save_history()
        print(f"💾 История обновлена ({len(self.history)} записей)")

if __name__ == "__main__":
    try:
        scanner = IPTVScanner()
        asyncio.run(scanner.run())
        print("\n✅ ВСЕ ГОТОВО! Плейлисты обновлены.")
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise
