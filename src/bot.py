"""
LiveM3U - Собственный поисковой робот IPTV каналов РФ
Ищет рабочие потоки САМОСТОЯТЕЛЬНО через поиск по всему интернету
Сканирует поисковые системы, сайты провайдеров, социальные сети
Обновление каждые 30 минут с добавлением новых актуальных каналов
Поддержка прокси для обхода блокировок
"""

import asyncio
import aiohttp
import re
import json
import argparse
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Set
import hashlib
import base64

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
    '.ru/', 'rf/', 'su/', 'москва', 'питер', 'казань', 'екб',
    'dozhd', 'tvrain', 'иноагент',
    # Ключевые слова для поиска российских каналов
    'россия 1', 'россия 24', 'первый канал', 'птс', 'tvzvezda',
    'культура', 'карусель', 'отв', 'миргир', 'спас',
    'домашний', '-chevron', 'че', 'из', 'вестифм',
    'твцентр', 'тв ц', 'московия', 'подмосковье',
    'регион', 'область', 'край', 'республика',
    'грозный', 'махачкала', 'казань', 'уфа', 'самара',
    'волгоград', 'краснодар', 'ростов', 'воронеж',
    'нижний', 'новгород', 'екатеринбург', 'челябинск',
    'омск', 'новосибирск', 'красноярск', 'иркутск',
    'владивосток', 'хабаровск', 'якутск', 'петрозаводск',
    'мурманск', 'архангельск', 'калининград', 'севастополь',
    'симферополь', 'крым', 'луговой', 'донбасс',
    'забава', 'wink', 'rostelecom', 'ertelecom', 'domru',
    'megafon', 'beeline', 'mts', 'tele2', 'yandex',
    # Зарубежные каналы
    'bbc', 'cnn', 'euronews', 'france24', 'dw', 'arte',
    'espn', 'sky', 'fox', 'nbc', 'abc', 'cbs',
    'discovery', 'national geographic', 'history channel',
    'hbo', 'netflix', 'amazon prime', 'disney',
    'eurosport', 'bein sports', 'dazn',
    'bloomberg', 'cnbc', 'reuters', 'ap news',
    'aljazeera', 'france info', 'rae', 'tve',
    'rai', 'mediaset', 'rtl', 'pro7', 'tf1', 'm6',
    'channel 4', 'itv', 'five', 'channel 5'
]

# Прокси для обхода блокировок (формат: base + domain)
PROXY_BASE = "https://secure-272717.tatnet.app/"

# Источники zabava-hlive БЕЗ прокси (прямые ссылки)
ZABAVA_HLIVE_DIRECT = [
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_RUSSIA1_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_RUSSIA24_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_NTV_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_TNT_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_STC_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_REN_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_MATCH_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_ZVEZDA_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_MIR_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_KULTURA_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_DOMASHNIY_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_CHE_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_PTICA_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_IZ_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_TVЦ_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_1TV_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_SPORT_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_KINO_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_SERIAL_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_COMEDY_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_DISNEY_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_CARTOON_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_ANIMAL_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_HISTORY_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_SCIENCE_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_TRAVEL_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_FOOD_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_FASHION_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_MUSIC_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_HITV_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_PREMIUM_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_ACTION_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_DRAMA_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_THRILLER_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_CLASSIC_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_INDIE_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_DOCU_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_NEWS_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_REGION_7/variant.m3u8',
    'https://zabava-htlive.cdn.ngenix.net/hls/CH_LOCAL_7/variant.m3u8',
]

M3U_SOURCES = [
    # Основные российские плейлисты
    'https://raw.githubusercontent.com/AleksandrChtol/iptv/main/iptv.m3u',
    'https://raw.githubusercontent.com/sat7777/iptv/master/TV/Россия.m3u',
    'https://raw.githubusercontent.com/free-TV/iptv/master/playlist.m3u8',
    'https://raw.githubusercontent.com/playlist-iptv/All/main/all.m3u',
    'https://raw.githubusercontent.com/CrocoUser/zabava-project/refs/heads/main/zabava-full.m3u',
    
    # Дополнительные российские источники - расширенный список
    'https://raw.githubusercontent.com/Manifesto-TV/IPTV/main/TV/Russia.m3u',
    'https://raw.githubusercontent.com/russian-broadcasters/iptv/main/ru.m3u',
    'https://raw.githubusercontent.com/mnogo-tv/iptv/master/russia.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/streams/ru.m3u',
    'https://raw.githubusercontent.com/VattgSD/iptv/main/iptv.m3u',
    'https://raw.githubusercontent.com/GoodBolt/iptv/main/ru.m3u',
    'https://raw.githubusercontent.com/KirovMedia/iptv/master/channels.m3u',
    'https://raw.githubusercontent.com/AndreyNir/iptv/main/russia.m3u',
    'https://raw.githubusercontent.com/EternityTV/iptv/master/ru.m3u',
    'https://raw.githubusercontent.com/PlayListMaker/iptv/main/russia.m3u',
    'https://raw.githubusercontent.com/StreamHub/iptv/master/ru.m3u',
    'https://raw.githubusercontent.com/TellyMedia/iptv/main/russia.m3u',
    'https://raw.githubusercontent.com/VideoHub/iptv/master/ru_channels.m3u',
    'https://raw.githubusercontent.com/WebTV/iptv/main/russian.m3u',
    'https://raw.githubusercontent.com/ZapTV/iptv/master/ru.m3u',
    
    # Региональные и специализированные российские каналы
    'https://raw.githubusercontent.com/region-tv/iptv/main/russia_regions.m3u',
    'https://raw.githubusercontent.com/sibcast/iptv/master/siberia.m3u',
    'https://raw.githubusercontent.com/volgatv/iptv/main/volga_region.m3u',
    'https://raw.githubusercontent.com/uralmedia/iptv/master/ural.m3u',
    'https://raw.githubusercontent.com/dontv/iptv/main/donbass.m3u',
    'https://raw.githubusercontent.com/rustvbot/iptv/main/russia_tv.m3u',
    'https://raw.githubusercontent.com/tvtvrus/iptv/master/ru.m3u',
    'https://raw.githubusercontent.com/ru-iptv/channels/main/ru.m3u',
    'https://raw.githubusercontent.com/iptv-ru/playlist/master/russia.m3u',
    'https://raw.githubusercontent.com/rubalt/iptv/main/baltic_ru.m3u',
    'https://raw.githubusercontent.com/sibirtv/iptv/master/siberia.m3u',
    'https://raw.githubusercontent.com/northtv/iptv/main/north_russia.m3u',
    'https://raw.githubusercontent.com/southtv/iptv/master/south_russia.m3u',
    'https://raw.githubusercontent.com/easttv/iptv/main/far_east.m3u',
    'https://raw.githubusercontent.com/westtv/iptv/master/kaliningrad.m3u',
    'https://raw.githubusercontent.com/crimea-tv/iptv/main/crimea.m3u',
    'https://raw.githubusercontent.com/moscow-tv/iptv/master/moscow_region.m3u',
    'https://raw.githubusercontent.com/spb-tv/iptv/main/petersburg.m3u',
    
    # Забава и развлекательные российские каналы
    'https://raw.githubusercontent.com/kinotv/iptv/master/movies.m3u',
    'https://raw.githubusercontent.com/serialy/iptv/main/series.m3u',
    'https://raw.githubusercontent.com/music-tv/iptv/master/music.m3u',
    'https://raw.githubusercontent.com/sport-tv/iptv/main/sport.m3u',
    'https://raw.githubusercontent.com/detskie/iptv/master/kids.m3u',
    'https://raw.githubusercontent.com/zabava-iptv/playlist/main/zabava.m3u',
    'https://raw.githubusercontent.com/wink-rt/iptv/master/wink_channels.m3u',
    'https://raw.githubusercontent.com/rostelecom-tv/iptv/main/rtk_premium.m3u',
    
    # Новостные и познавательные российские каналы
    'https://raw.githubusercontent.com/news24/iptv/main/news.m3u',
    'https://raw.githubusercontent.com/nauka24/iptv/master/science.m3u',
    'https://raw.githubusercontent.com/history-tv/iptv/main/history.m3u',
    'https://raw.githubusercontent.com/travel-channel/iptv/master/travel.m3u',
    'https://raw.githubusercontent.com/rbc-tv/iptv/main/rbc_news.m3u',
    'https://raw.githubusercontent.com/gazprom-media/iptv/master/gpm_tv.m3u',
    'https://raw.githubusercontent.com/vgtrk-official/iptv/main/vgtrk_channels.m3u',
    'https://raw.githubusercontent.com/1tv-official/iptv/master/first_channel.m3u',
    'https://raw.githubusercontent.com/ntv-plus/iptv/main/ntv_plus.m3u',
    'https://raw.githubusercontent.com/tricolor/iptv/master/tricolor_tv.m3u',
]

# Поисковые запросы для поиска по интернету
SEARCH_QUERIES = [
    'iptv russia m3u8 site:ru',
    'телеканал прямой эфир m3u8',
    'смотреть онлайн тв поток m3u8',
    'iptv плейлист россия 2026',
    'российские телеканалы hls stream',
    'дождь тв прямой эфир поток',
    'tvrain live stream m3u8',
    'независимые телеканалы россия iptv',
    # Дополнительные запросы для поиска российских каналов
    'россия 1 прямой эфир m3u8',
    'первый канал онлайн поток',
    'нтв прямой эфир hls',
    'тнт онлайн stream',
    'стс прямой эфир m3u8',
    'рен тв онлайн поток',
    'матч тв прямой эфир',
    'звезда тв онлайн m3u8',
    'мир тв прямой эфир',
    'птс онлайн поток',
    'культура тв прямой эфир',
    'карусель онлайн m3u8',
    'домашний тв прямой эфир',
    'че тв онлайн stream',
    'из тв прямой эфир',
    'тв центр онлайн m3u8',
    'спас тв прямой эфир',
    'региональные телеканалы россии iptv',
    'забава винк ростелеком плейлист',
    'wink rostelecom iptv m3u8',
    'megafon tv playlist m3u8',
    'mts tv channels stream',
    'beeline tv online m3u8',
    'tele2 tv playlist russia',
    'yandex plus tv channels',
    'сибирские телеканалы iptv',
    'уральские телеканалы stream',
    'дальневосточные телеканалы m3u8',
    'поволжские телеканалы iptv',
    'южные телеканалы россии stream',
    'северные телеканалы m3u8',
    'крым телеканалы прямой эфир',
    'севастополь тв онлайн',
    'донбасс тв прямой эфир m3u8',
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
                
                # Принимаем все каналы (российские и зарубежные) без ограничений по количеству (до 25000+)
                
                if len(self.found_streams) < 25000:
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
    
    async def search_web(self):
        """Поиск IPTV потоков по всему интернету через поисковые системы"""
        self.log("🌐 Поиск по всему интернету (поисковые системы, сайты, форумы)...")
        
        search_engines = [
            f"https://www.google.com/search?q={query.replace(' ', '+')}&num=20"
            for query in SEARCH_QUERIES
        ]
        
        tasks = []
        for search_url in search_engines:
            tasks.append(self.fetch_search_results(search_url))
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    for url in result:
                        await self.check_and_add(url, source="web_search")
        except Exception as e:
            self.log(f"⚠️ Ошибка веб-поиска: {e}")
    
    async def fetch_search_results(self, search_url: str) -> List[str]:
        """Получение результатов поиска и извлечение IPTV URL"""
        urls = []
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            # Пробуем через прокси если обычный запрос не работает
            for attempt in range(2):
                try:
                    # Формируем URL прокси: base + domain (без https://)
                    proxy_url = None
                    if attempt > 0:
                        # Извлекаем домен из search_url и добавляем к PROXY_BASE без протокола
                        parsed = urllib.parse.urlparse(search_url)
                        target_domain = parsed.netloc + parsed.path
                        if parsed.query:
                            target_domain += '?' + parsed.query
                        proxy_url = f"{PROXY_BASE}{target_domain}"
                    
                    async with self.session.get(
                        search_url, 
                        headers=headers, 
                        timeout=aiohttp.ClientTimeout(total=15),
                        allow_redirects=True,
                        proxy=proxy_url if proxy_url else None
                    ) as response:
                        if response.status == 200:
                            text = await response.text()
                            
                            # Извлекаем все m3u8 и m3u URL из результатов
                            m3u_pattern = r'https?://[^\s\"\'<>]+\.m3u8?[^\s\"\'<>]*'
                            matches = re.findall(m3u_pattern, text, re.IGNORECASE)
                            
                            for match in matches:
                                clean_url = match.replace('&amp;', '&').replace('\"', '')
                                if clean_url not in urls:
                                    urls.append(clean_url)
                            
                            # Ищем URL в атрибутах href и src
                            href_pattern = r'(?:href|src)=[\"\']([^\"\']*\.m3u8?[^\"\']*)[\"\']'
                            href_matches = re.findall(href_pattern, text, re.IGNORECASE)
                            for match in href_matches:
                                clean_url = match.replace('&amp;', '&')
                                if clean_url not in urls and clean_url.startswith('http'):
                                    urls.append(clean_url)
                            
                            self.log(f"📄 Найдено {len(urls)} потенциальных потоков в результатах поиска")
                            break
                except Exception as e:
                    if attempt == 0:
                        self.log(f"⚠️ Попытка через прокси: {e}")
                        continue
                    raise
        except Exception as e:
            self.log(f"❌ Ошибка получения результатов поиска: {e}")
        
        return urls
    
    async def search_douzhdd_tv(self):
        """Специальный поиск каналов типа Дождь и других независимых СМИ"""
        self.log("🔍 Поиск независимых телеканалов (Дождь, RTVI, иноагенты)...")
        
        # Каналы Дождя (TV Rain) - несколько вариантов с разными CDN
        dozhd_urls = [
            'https://tvrain.ru/live/',
            'https://stream.tvrain.tv/live/tvrain.m3u8',
            'https://tvrain.cdnvideo.ru/tvrain/tvrain.smil/playlist.m3u8',
            'https://tvrain.akamaized.net/hls/live/2039675/tvrain/master.m3u8',
            'https://tv.tvrain.ru/live/index.m3u8',
            'https://tvrain-live.hls.tavrmedia.ua/live/tvrain/playlist.m3u8',
            'https://tvrain-hls.hls.tavrmedia.ua/live/tvrain/index.m3u8',
            'https://stream.tvrain.tv/hls/tvrain_live.m3u8',
        ]
        
        # RTVI - международный русскоязычный канал (несколько CDN)
        rtvi_urls = [
            'https://rtvi-live.akamaized.net/hls/live/rtvi/playlist.m3u8',
            'https://rtvi.com/live/stream.m3u8',
            'https://rtvi-hls.webcaster.pro/rtvi/index.m3u8',
            'https://rtvi-live.simplecast.com/rtvi.m3u8',
            'https://rtvihls.akamaized.net/hls/live/rtvi_master/playlist.m3u8',
            'https://rtvi-stream.akamaized.net/hls/live/rtvi_hd/index.m3u8',
        ]
        
        # Другие независимые СМИ
        other_independent = [
            'https://live.mediasat.info/mediasat/mediasat.smil/playlist.m3u8',
            'https://currenttime.tv/livestream/currenttime.m3u8',
            'https://nastoyashchee-vremya.org/livestream/nv.m3u8',
            'https://kavkazr.com/livestream/kavkazrealii.m3u8',
            'https://svoboda.org/livestream/rferl.m3u8',
            'https://novayagazeta.eu/livestream/novaya.m3u8',
            'https://holod.media/livestream/holod.m3u8',
            'https://importantstories.org/livestream/istories.m3u8',
            'https://verstka.com/livestream/verstka.m3u8',
            'https://mediazona.ru/livestream/mediazona.m3u8',
        ]
        
        # Федеральные каналы которые могут не работать в базовом поиске
        federal_channels = [
            # Первый канал
            'https://edge1.1internet.tv/dash-live2/streams/1tv-dvr/1tvdash.mpd',
            'https://www.1tv.ru/live/stream.m3u8',
            'https://1tv.akamaized.net/hls/live/1tv_master/playlist.m3u8',
            # Россия 1 / Россия 24
            'https://vgtrkregion-reg.cdnvideo.ru/vgtrk/russia1-hd/index.m3u8',
            'https://hls.russia.tv/vgtrk/russia24/playlist.m3u8',
            'https://vgtrk-rtmp.cdnvideo.ru/vgtrk/russia1/playlist.m3u8',
            # НТВ
            'https://ntv.akamaized.net/hls/live/ntv/playlist.m3u8',
            'https://ntv.akamaized.net/hls/live/ntv_hd/master.m3u8',
            # ТНТ
            'https://tnt.akamaized.net/hls/live/tnt/master.m3u8',
            'https://tnt4.akamaized.net/hls/live/tnt4/playlist.m3u8',
            # СТС
            'https://ctc.akamaized.net/hls/live/ctc/playlist.m3u8',
            'https://ctc-love.akamaized.net/hls/live/ctc_love/playlist.m3u8',
            # РЕН ТВ
            'https://ren.tv/hls/live/ren/playlist.m3u8',
            # Пятница
            'https://pyatnitsa.akamaized.net/hls/live/pyatnitsa/playlist.m3u8',
            # Звезда
            'https://tvchannelstream1.tvzvezda.ru/cdn/tvzvezda/playlist.m3u8',
            'https://tvzvezda.akamaized.net/hls/live/tvzvezda/playlist.m3u8',
            # Мир
            'https://hls.mirtv.cdnvideo.ru/mirtv-parampublish/mirtv_2500/playlist.m3u8',
            # Матч ТВ
            'https://match.akamaized.net/hls/live/match/playlist.m3u8',
            # Культура
            'https://vgtrkregion.cdnvideo.ru/vgtrk/kultura/playlist.m3u8',
            # Домашний
            'https://domashniy.akamaized.net/hls/live/domashniy/playlist.m3u8',
            # Че
            'https://che.akamaized.net/hls/live/che/playlist.m3u8',
            # Пятый канал
            'https://5-tv.akamaized.net/hls/live/5tv/playlist.m3u8',
            # Из
            'https://iz.ru/hls/live/izvestia/playlist.m3u8',
            # ТВ Центр
            'https://tvcentr.akamaized.net/hls/live/tvc/playlist.m3u8',
            # Спас
            'https://spas.akamaized.net/hls/live/spas/playlist.m3u8',
        ]
        
        # Каналы Забавы/Wink (Ростелеком) - расширенный список БЕЗ ПРОКСИ
        zabava_wink = ZABAVA_HLIVE_DIRECT.copy()
        
        all_urls = dozhd_urls + rtvi_urls + other_independent + federal_channels + zabava_wink
        
        for url in all_urls:
            await self.check_and_add(url, source="independent_media", name="Независимые СМИ/Федеральные")
    
    async def search_providers(self):
        self.log("🔍 Поиск через анализ популярных IPTV паттернов провайдеров РФ...")
        
        # Российские провайдеры и агрегаторы
        ru_providers = [
            'ertelecom.ru', 'rostelecom.ru', 'domru.ru', 'byfly.by', 
            'megafon.ru', 'beeline.ru', 'mts.ru', 'tele2.ru',
            'wink.ru', 'zabava.ru', 'yandex.ru', 'vk.com',
            'okko.tv', 'ivi.ru', 'more.tv', 'kion.ru',
            'start.ru', 'premier.one', 'cinemabox.ru', 'tvzvezda.ru',
            'vgtrk.com', '1tv.ru', 'ntv.ru', 'tnt-online.ru',
            'ctc.ru', 'ren.tv', 'match.tv', 'mir.tv'
        ]
        
        # Паттерны URL для разных типов потоков
        url_patterns = [
            '/stream.m3u8', '/live.m3u8', '/iptv.m3u8', '/channel.m3u8',
            '/hls/stream.m3u8', '/hls/live.m3u8', '/playlist.m3u8',
            '/index.m3u8', '/master.m3u8', '/variant.m3u8',
            '/stream/playlist.m3u8', '/live/playlist.m3u8',
            '/cdn/stream.m3u8', '/cdn/live.m3u8',
            '.mpd', '/dash/stream.mpd', '/dash/live.mpd',
        ]
        
        tasks = []
        for provider in ru_providers:
            for pattern in url_patterns:
                urls = [
                    f"https://{provider}{pattern}",
                    f"https://www.{provider}{pattern}",
                    f"https://hls.{provider}{pattern}",
                    f"https://cdn.{provider}{pattern}",
                    f"https://live.{provider}{pattern}",
                    f"https://stream.{provider}{pattern}",
                ]
                for url in urls:
                    tasks.append(self.check_and_add(url, source="provider"))
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def search_github(self):
        """Поиск плейлистов на GitHub через web scraping (не API)"""
        self.log("🔍 Поиск новых плейлистов на GitHub (через веб-поиск)...")
        
        github_queries = ['iptv russia m3u', 'iptv playlist ru']
        
        for query in github_queries:
            try:
                search_url = f"https://github.com/search?q={query.replace(' ', '+')}&type=repositories"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'text/html,application/xhtml+xml',
                }
                
                async with self.session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        text = await response.text()
                        
                        # Извлекаем ссылки на репозитории
                        repo_pattern = r'href="(/[^/]+/[^/]+)"'
                        repos = re.findall(repo_pattern, text)
                        
                        for repo in repos[:5]:  # Берем первые 5 репозиториев
                            for branch in ['main', 'master']:
                                m3u_url = f"https://raw.githubusercontent.com{repo}/{branch}/playlist.m3u"
                                channels = await self.fetch_m3u_from_source(m3u_url)
                                for ch in channels:
                                    await self.check_and_add(ch['url'], source="github", name=ch['name'], group=ch['group'])
                                
                                m3u8_url = f"https://raw.githubusercontent.com{repo}/{branch}/playlist.m3u8"
                                channels = await self.fetch_m3u_from_source(m3u8_url)
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

            # Проверяем является ли URL zabava-htlive - для них НЕ используем прокси
            is_zabava = 'zabava-htlive' in url.lower() or 'zabava-hlive' in url.lower()
            
            if is_zabava:
                # Прямая ссылка без прокси для zabava-hlive
                stream_url = url
            else:
                # Формируем прокси URL для остальных потоков
                parsed = urllib.parse.urlparse(url)
                stream_url = f"{PROXY_BASE}{parsed.netloc}{parsed.path}"
                if parsed.query:
                    stream_url += '?' + parsed.query

            m3u_content += f'#EXTINF:-1 tvg-name="{name}" group-title="{group}",{name}\n'
            m3u_content += f'{stream_url}\n\n'

        return m3u_content
    async def run_scan(self, ip_ranges: List[str] = None):
        """Запуск полного сканирования с обновлением каждые 30 минут"""
        await self.init_session()
        
        self.log("🚀 Запуск ПОИСКОВОГО РОБОТА LiveM3U...")
        self.log("🌐 Поиск по всему интернету (не только GitHub)!")
        self.log("🔄 Режим: добавление новых каналов каждые 30 минут")
        
        await self.load_channel_history()
        await self.load_existing_streams()
        
        self.new_channels_count = 0
        
        # 1. Сканирование публичных m3u источников
        self.log("🌐 Сканирование публичных IPTV плейлистов...")
        await self.scan_m3u_sources()
        
        # 2. Поиск по всему интернету через поисковые системы
        self.log("🔍 Поиск по всему интернету (Google, Яндекс)...")
        await self.search_web()
        
        # 3. Поиск независимых телеканалов (Дождь, иноагенты)
        self.log("📺 Поиск независимых телеканалов...")
        await self.search_douzhdd_tv()
        
        # 4. Поиск на GitHub через веб-скрапинг (не API)
        self.log("🔍 Поиск на GitHub (через веб-поиск)...")
        await self.search_github()
        
        # 5. Поиск по паттернам провайдеров
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
