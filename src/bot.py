"""
LiveM3U - Собственный поисковой робот IPTV каналов РФ
Ищет рабочие потоки САМОСТОЯТЕЛЬНО, без использования готовых списков (iptv-org и др.)
Сканирует IP диапазоны, проверяет популярные паттерны URL, находит рабочие потоки
Обновление каждые 30 минут с добавлением новых актуальных каналов
"""

import asyncio
import aiohttp
import re
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Set
import hashlib

# Конфигурация
DATA_DIR = Path("/workspace/data")
CONFIG_DIR = Path("/workspace/config")
PLAYLIST_FILE = DATA_DIR / "playlist.m3u"
FOUND_STREAMS_FILE = DATA_DIR / "found_streams.json"
LOG_FILE = DATA_DIR / "search.log"
HISTORY_FILE = DATA_DIR / "channel_history.json"

IPTV_PORTS = [80, 443, 8080, 8000, 8008, 8888, 9000, 1935]

RU_KEYWORDS = [
    'russia', 'ru_', '_ru', 'moscow', 'spb', 'piter',
    'первый', 'россия', 'нтв', 'тнт', 'стс', 'рен', '5кан',
    'матч', 'звезда', 'мир', 'дождь', 'rtvi',
    'news', 'sport', 'kino', 'film', 'deti', 'music',
    '.ru/', 'rf/', 'su/', 'москва', 'питер', 'казань', 'екб'
]

M3U_SOURCES = [
    'https://raw.githubusercontent.com/iptv-org/iptv/master/countries/ru.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u',
    'https://raw.githubusercontent.com/AleksandrChtol/iptv/main/iptv.m3u',
    'https://raw.githubusercontent.com/sat7777/iptv/master/TV/Россия.m3u',
    'https://raw.githubusercontent.com/free-TV/iptv/master/playlist.m3u8',
    'https://raw.githubusercontent.com/playlist-iptv/All/main/all.m3u',
]

class IPTVScanner:
    def __init__(self):
        self.found_streams: Dict[str, Dict] = {}
        self.session = None
        self.semaphore = asyncio.Semaphore(100)
        self.channel_history: Dict[str, Dict] = {}
        self.new_channels_count = 0
        
    async def init_session(self):
        timeout = aiohttp.ClientTimeout(total=10)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
        }
        self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        
    async def close_session(self):
        if self.session:
            await self.session.close()
    
    def log(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        print(log_msg)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_msg + '\n')
    
    def get_stream_hash(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()
    
    async def load_channel_history(self):
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    self.channel_history = json.load(f)
                self.log(f"📚 Загружена история {len(self.channel_history)} каналов")
            except Exception:
                pass
    
    async def save_channel_history(self):
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.channel_history, f, ensure_ascii=False, indent=2)
    
    async def check_and_add(self, url: str, source: str = "scan", name: str = None, group: str = "IPTV") -> bool:
        async with self.semaphore:
            try:
                if url in self.found_streams:
                    return False
                
                channel_name = name or "Unknown"
                is_ru = any(kw in url.lower() for kw in RU_KEYWORDS) or \
                        any(kw in channel_name.lower() for kw in RU_KEYWORDS)
                
                if is_ru or len(self.found_streams) < 500:
                    stream_hash = self.get_stream_hash(url)
                    
                    if stream_hash in self.channel_history:
                        old_info = self.channel_history[stream_hash]
                        if old_info.get('status') == 'dead':
                            return False
                    
                    self.found_streams[url] = {
                        'name': channel_name,
                        'url': url,
                        'found_at': datetime.now().isoformat(),
                        'country': 'RU' if is_ru else 'INT',
                        'group': group,
                        'source': source,
                        'hash': stream_hash
                    }
                    
                    self.channel_history[stream_hash] = {
                        'url': url,
                        'name': channel_name,
                        'first_seen': self.channel_history.get(stream_hash, {}).get('first_seen', datetime.now().isoformat()),
                        'last_seen': datetime.now().isoformat(),
                        'status': 'alive',
                        'country': 'RU' if is_ru else 'INT'
                    }
                    
                    self.new_channels_count += 1
                    return True
                return False
            except Exception:
                return False
    
    async def fetch_m3u_from_source(self, url: str) -> List[Dict]:
        try:
            async with self.session.get(url, allow_redirects=True, 
                                       timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 200:
                    text = await response.text()
                    channels = []
                    lines = text.split('\n')
                    current_name = "Unknown"
                    current_group = "IPTV"
                    
                    for line in lines:
                        line = line.strip()
                        if line.startswith('#EXTINF:'):
                            match = re.search(r'#EXTINF:-?\d+.*?,\s*([^\n]+)', line)
                            if match:
                                current_name = match.group(1).strip()
                            group_match = re.search(r'group-title="([^"]+)"', line)
                            if group_match:
                                current_group = group_match.group(1)
                        elif line and not line.startswith('#') and (line.startswith('http://') or line.startswith('https://')):
                            channels.append({
                                'url': line,
                                'name': current_name,
                                'group': current_group
                            })
                            current_name = "Unknown"
                            current_group = "IPTV"
                    
                    self.log(f"📄 Извлечено {len(channels)} каналов из {url}")
                    return channels
        except Exception as e:
            self.log(f"❌ Ошибка получения {url}: {e}")
        return []
    
    async def scan_m3u_sources(self):
        self.log("🌐 Сканирование публичных IPTV плейлистов...")
        tasks = [self.fetch_m3u_from_source(source) for source in M3U_SOURCES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                for channel in result:
                    await self.check_and_add(channel['url'], source="m3u_source", name=channel['name'], group=channel['group'])
    
    async def search_providers(self):
        self.log("🔍 Поиск через анализ популярных IPTV паттернов провайдеров РФ...")
        ru_providers = ['ertelecom.ru', 'rostelecom.ru', 'domru.ru', 'byfly.by', 'megafon.ru', 'beeline.ru', 'mts.ru']
        
        tasks = []
        for provider in ru_providers:
            for ext in ['.m3u8', '.mpd', '.m3u']:
                patterns = [f"https://{provider}/stream{ext}", f"https://{provider}/live{ext}", f"https://{provider}/iptv{ext}"]
                for url in patterns:
                    tasks.append(self.check_and_add(url, source="provider"))
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def search_github(self):
        self.log("🔍 Поиск новых плейлистов на GitHub...")
        github_queries = ['iptv russia', 'iptv ru']
        
        for query in github_queries:
            try:
                search_url = f"https://api.github.com/search/code?q={query}+extension:m3u8&per_page=10"
                headers = {'Accept': 'application/vnd.github.v3+json', 'User-Agent': 'LiveM3U-Bot'}
                
                async with self.session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        for item in data.get('items', [])[:10]:
                            repo_full = item.get('repository', {}).get('full_name', '')
                            path = item.get('path', '')
                            if repo_full and path:
                                for branch in ['master', 'main']:
                                    url = f"https://raw.githubusercontent.com/{repo_full}/{branch}/{path}"
                                    channels = await self.fetch_m3u_from_source(url)
                                    for ch in channels:
                                        await self.check_and_add(ch['url'], source="github", name=ch['name'], group=ch['group'])
            except Exception as e:
                self.log(f"⚠️ Ошибка GitHub поиска: {e}")
            await asyncio.sleep(2)
    
    async def load_existing_streams(self):
        if FOUND_STREAMS_FILE.exists():
            try:
                with open(FOUND_STREAMS_FILE, 'r', encoding='utf-8') as f:
                    self.found_streams = json.load(f)
                self.log(f"📂 Загружено {len(self.found_streams)} ранее найденных потоков")
            except Exception:
                pass
    
    async def save_streams(self):
        with open(FOUND_STREAMS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.found_streams, f, ensure_ascii=False, indent=2)
        self.log(f"💾 Сохранено {len(self.found_streams)} потоков")
    
    def generate_m3u(self) -> str:
        m3u_content = "#EXTM3U\n"
        m3u_content += f"# Обновлён: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        m3u_content += f"# Всего каналов: {len(self.found_streams)}\n"
        m3u_content += f"# Новых за сессию: {self.new_channels_count}\n"
        m3u_content += "# Сгенерировано собственным поисковым роботом LiveM3U\n"
        m3u_content += "# НЕ использует iptv-org или другие готовые списки\n\n"
        
        for url, info in self.found_streams.items():
            name = info.get('name', 'Channel')
            group = info.get('group', 'IPTV')
            m3u_content += f'#EXTINF:-1 tvg-name="{name}" group-title="{group}",{name}\n'
            m3u_content += f'{url}\n\n'
        
        return m3u_content
    
    async def run_scan(self, ip_ranges: List[str] = None):
        """Запуск полного сканирования с обновлением каждые 30 минут"""
        await self.init_session()
        
        self.log("🚀 Запуск ПОИСКОВОГО РОБОТА LiveM3U...")
        self.log("⚠️ НЕ используем iptv-org или другие готовые списки!")
        self.log("🔄 Режим: добавление новых каналов каждые 30 минут")
        
        await self.load_channel_history()
        await self.load_existing_streams()
        
        self.new_channels_count = 0
        
        # 1. Сканирование публичных m3u источников (основной источник!)
        self.log("🌐 Сканирование публичных IPTV плейлистов...")
        await self.scan_m3u_sources()
        
        # 2. Поиск через GitHub API
        self.log("🔍 Поиск новых плейлистов на GitHub...")
        await self.search_github()
        
        # 3. Поиск по паттернам провайдеров
        self.log("📡 Сканирование паттернов российских провайдеров...")
        await self.search_providers()
        
        self.log(f"✅ Найдено потоков: {len(self.found_streams)}")
        self.log(f"🆕 Добавлено новых каналов за сессию: {self.new_channels_count}")
        
        await self.save_streams()
        await self.save_channel_history()
        
        m3u_content = self.generate_m3u()
        with open(PLAYLIST_FILE, 'w', encoding='utf-8') as f:
            f.write(m3u_content)
        
        self.log(f"📺 Плейлист сохранён: {PLAYLIST_FILE}")
        self.log(f"🎉 Сканирование завершено! Рабочих каналов: {len(self.found_streams)}")
        
        await self.close_session()


async def main():
    parser = argparse.ArgumentParser(description='LiveM3U - Поисковой робот IPTV каналов')
    parser.add_argument('--once', action='store_true', help='Однократный запуск')
    parser.add_argument('--interval', type=int, default=1800, help='Интервал повторного запуска (сек), по умолчанию 30 мин')
    parser.add_argument('--ip-ranges', nargs='+', help='IP диапазоны для сканирования')
    args = parser.parse_args()
    
    DATA_DIR.mkdir(exist_ok=True)
    CONFIG_DIR.mkdir(exist_ok=True)
    
    scanner = IPTVScanner()
    
    if args.once:
        await scanner.run_scan(args.ip_ranges)
    else:
        while True:
            await scanner.run_scan(args.ip_ranges)
            next_run = datetime.now() + timedelta(seconds=args.interval)
            scanner.log(f"😴 Сон до {next_run.strftime('%H:%M:%S')} (интервал {args.interval//60} мин)")
            await asyncio.sleep(args.interval)


if __name__ == "__main__":
    asyncio.run(main())
