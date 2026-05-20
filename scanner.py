#!/usr/bin/env python3
"""
LiveM3U - Поисковой робот IPTV каналов
Сканер для GitHub Actions - обновляет плейлисты каждые 30 минут
Ищет каналы на сайтах (не YouTube API), работает с прокси
Не удаляет старые каналы, только добавляет новые рабочие
"""

import asyncio
import aiohttp
import re
import json
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set
import hashlib
import os

# Конфигурация
DATA_DIR = Path("data")
PLAYLIST_FILE = DATA_DIR / "playlist.m3u"
FOUND_STREAMS_FILE = DATA_DIR / "found_streams.json"
HISTORY_FILE = DATA_DIR / "channel_history.json"
LOG_FILE = DATA_DIR / "search.log"

# Прокси настройки из environment
PROXY_HOST = os.environ.get("PROXY_HOST", "secure-272717.tatnet.app")
PROXY_PORT = os.environ.get("PROXY_PORT", "8080")
PROXY_BASE = f"https://{PROXY_HOST}/"

# Исключаем этот домен из плейлистов
EXCLUDED_DOMAIN = "zabava-hlive.nginx.net"

# Ключевые слова для поиска русскоязычных и международных каналов
RU_KEYWORDS = [
    'russia', 'ru_', '_ru', 'moscow', 'spb', 'piter',
    'первый', 'россия', 'нтв', 'тнт', 'стс', 'рен', '5кан',
    'матч', 'звезда', 'мир', 'дождь', 'rtvi',
    'news', 'sport', 'kino', 'film', 'deti', 'music',
    '.ru/', 'rf/', 'su/', 'москва', 'питер', 'казань', 'екб',
    'россия 1', 'россия 24', 'первый канал', 'птс', 'tvzvezda',
    'культура', 'карусель', 'отв', 'миргир', 'спас',
    'домашний', 'че', 'из', 'вестифм', 'твцентр',
    'забава', 'wink', 'rostelecom', 'ertelecom', 'domru',
    'megafon', 'beeline', 'mts', 'tele2', 'yandex',
    'bbc', 'cnn', 'euronews', 'france24', 'dw', 'arte',
    'espn', 'sky', 'fox', 'nbc', 'abc', 'cbs',
    'discovery', 'national geographic', 'history channel',
    'hbo', 'netflix', 'amazon prime', 'disney',
    'eurosport', 'bein sports', 'dazn',
    'bloomberg', 'cnbc', 'reuters', 'ap news',
    'aljazeera', 'france info', 'rai', 'tve',
    'rtl', 'pro7', 'tf1', 'm6', 'channel 4', 'itv'
]

# Приоритетные каналы которые должны быть в плейлисте (актуальные рабочие ссылки)
PRIORITY_CHANNELS = [
    {
        'url': 'https://wl.tvrain.tv/transcode/ngrp:ses_all/playlist.m3u8',
        'name': 'Дождь',
        'group': 'News'
    },
    {
        'url': 'https://stream.tvrain.tv/live/tvrain.m3u8',
        'name': 'Дождь (альтернативный)',
        'group': 'News'
    },
    {
        'url': 'https://stream.tvrain.tv/hls/tvrain_live.m3u8',
        'name': 'Дождь (резервный)',
        'group': 'News'
    },
]

# Источники m3u плейлистов для сканирования - МАКСИМАЛЬНО РАСШИРЕННЫЙ СПИСОК
M3U_SOURCES = [
    # === РОССИЙСКИЕ IPTV ПЛЕЙЛИСТЫ (ОСНОВНЫЕ) ===
    'https://raw.githubusercontent.com/AleksandrChtol/iptv/main/iptv.m3u',
    'https://raw.githubusercontent.com/sat7777/iptv/master/TV/Россия.m3u',
    'https://raw.githubusercontent.com/sat7777/iptv/master/TV/Украина.m3u',
    'https://raw.githubusercontent.com/sat7777/iptv/master/TV/Беларусь.m3u',
    'https://raw.githubusercontent.com/sat7777/iptv/master/TV/Казахстан.m3u',
    'https://raw.githubusercontent.com/free-TV/iptv/master/playlist.m3u8',
    'https://raw.githubusercontent.com/playlist-iptv/All/main/all.m3u',
    'https://raw.githubusercontent.com/CrocoUser/zabava-project/refs/heads/main/zabava-full.m3u',
    'https://raw.githubusercontent.com/CrocoUser/zabava-project/refs/heads/main/zabava-reg.m3u',
    'https://raw.githubusercontent.com/Manifesto-TV/IPTV/main/TV/Russia.m3u',
    'https://raw.githubusercontent.com/Manifesto-TV/IPTV/main/TV/Ukraine.m3u',
    'https://raw.githubusercontent.com/Manifesto-TV/IPTV/main/TV/Belarus.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/streams/ru.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/iptv.m3u',
    'https://raw.githubusercontent.com/jnk0le/iptv-ru/main/playlist.m3u',
    'https://raw.githubusercontent.com/Evmenkov/iptv/main/iptv.m3u',
    'https://raw.githubusercontent.com/vasilyguk/iptv/main/playlist.m3u',
    'https://raw.githubusercontent.com/maglite/iptv/main/russia.m3u',
    'https://raw.githubusercontent.com/QuickLink/iptv/main/playlist.m3u',
    'https://raw.githubusercontent.com/black-bell/iptv/main/ru.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/countries/ru.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/countries/ua.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/countries/by.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/countries/kz.m3u',
    
    # === ДОПОЛНИТЕЛЬНЫЕ РОССИЙСКИЕ ИСТОЧНИКИ ===
    'https://raw.githubusercontent.com/nickvsn/iptv/main/iptv.m3u',
    'https://raw.githubusercontent.com/ihaveamac/iptv/main/iptv.m3u',
    'https://raw.githubusercontent.com/AndreyKuznetsov/iptv/main/playlist.m3u',
    'https://raw.githubusercontent.com/dmitry-v/iptv/master/russia.m3u',
    'https://raw.githubusercontent.com/iptv-ru/iptv/main/playlist.m3u',
    'https://raw.githubusercontent.com/russian-iptv/playlist/main/all.m3u',
    'https://raw.githubusercontent.com/iptv-source/iptv/main/ru.m3u',
    'https://raw.githubusercontent.com/streaming-tv/iptv/master/russia.m3u',
    'https://raw.githubusercontent.com/tv-channels/iptv/main/cis.m3u',
    'https://raw.githubusercontent.com/postpos/iptv/main/playlist.m3u',
    'https://raw.githubusercontent.com/kanal/iptv/master/russia.m3u',
    'https://raw.githubusercontent.com/telecard/iptv/main/channels.m3u',
    'https://raw.githubusercontent.com/ntv-plus/iptv/main/playlist.m3u',
    'https://raw.githubusercontent.com/tricolor/iptv/main/channels.m3u',
    'https://raw.githubusercontent.com/ertelecom/iptv/main/domru.m3u',
    'https://raw.githubusercontent.com/rostelecom/iptv/main/wink.m3u',
    'https://raw.githubusercontent.com/megafon/iptv/main/tv.m3u',
    'https://raw.githubusercontent.com/beeline/iptv/main/channels.m3u',
    'https://raw.githubusercontent.com/mts/iptv/main/tv.m3u',
    'https://raw.githubusercontent.com/tele2/iptv/main/channels.m3u',
    
    # === МЕЖДУНАРОДНЫЕ ПЛЕЙЛИСТЫ ===
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/us.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/gb.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/de.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/fr.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/es.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/it.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/tr.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/ua.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/kz.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/by.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/lt.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/lv.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/ee.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/pl.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/cz.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/sk.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/hu.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/ro.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/bg.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/rs.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/hr.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/si.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/gr.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/cn.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/jp.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/kr.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/in.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/br.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/ar.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/mx.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/ca.m3u',
    'https://raw.githubusercontent.com/IptvOrg/iptv/master/playlists/au.m3u',
    
    # === КАТЕГОРИИ ===
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/news.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/movies.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/sports.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/kids.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/music.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/documentary.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/entertainment.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/education.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/lifestyle.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/series.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/science.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/religion.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/outdoor.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/automotive.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/travel.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/weather.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/business.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/culture.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/fashion.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/categories/food.m3u',
    
    # === СПЕЦИАЛЬНЫЕ ИСТОЧНИКИ ===
    'https://raw.githubusercontent.com/FreeIPTV/channels/main/ru.m3u',
    'https://raw.githubusercontent.com/FreeIPTV/channels/main/ua.m3u',
    'https://raw.githubusercontent.com/FreeIPTV/channels/main/by.m3u',
    'https://raw.githubusercontent.com/FreeIPTV/channels/main/kz.m3u',
    'https://raw.githubusercontent.com/github/free-iptv/master/iptv.m3u',
    'https://raw.githubusercontent.com/IPTV-Org/iptv-ru/main/playlist.m3u',
    'https://raw.githubusercontent.com/RussianIPTV/channels/main/all.m3u',
    'https://raw.githubusercontent.com/CIS-IPTV/channels/main/playlist.m3u',
    'https://raw.githubusercontent.com/EuroIPTV/channels/main/europe.m3u',
    'https://raw.githubusercontent.com/AsiaIPTV/channels/main/asia.m3u',
]

# Поисковые запросы для поиска потоков на сайтах - МАКСИМАЛЬНО РАСШИРЕННЫЙ СПИСОК
SEARCH_QUERIES = [
    # === ЗАПРОСЫ ДЛЯ КАНАЛА ДОЖДЬ (ПРИОРИТЕТ) ===
    'дождь тв прямой эфир поток m3u8',
    'tvrain live stream m3u8',
    'tvrain.tv playlist.m3u8',
    'wl.tvrain.tv transcode playlist',
    'дождь новости прямой эфир hls',
    'tvrain hls stream 2025 2026',
    'дождь тв онлайн бесплатно m3u8',
    'tvrain akamaized cloudfront',
    
    # === ОБЩИЕ РОССИЙСКИЕ IPTV ЗАПРОСЫ ===
    'iptv russia m3u8 site:ru',
    'телеканал прямой эфир m3u8',
    'смотреть онлайн тв поток m3u8',
    'iptv плейлист россия 2025 2026',
    'российские телеканалы hls stream',
    'независимые телеканалы россия iptv',
    'бесплатные iptv каналы россия m3u',
    'рабочие iptv плейлисты 2026',
    'iptv подписка бесплатно m3u8',
    'онлайн тв россия hls',
    
    # === ОСНОВНЫЕ ФЕДЕРАЛЬНЫЕ КАНАЛЫ ===
    'россия 1 прямой эфир m3u8',
    'первый канал онлайн поток hls',
    'нтв прямой эфир hls stream',
    'тнт онлайн stream m3u8',
    'стс прямой эфир m3u8',
    'рен тв онлайн поток',
    'матч тв прямой эфир hls',
    'звезда тв онлайн m3u8',
    'мир тв прямой эфир stream',
    'птс культура карусель м3у8',
    'спас домашний че из м3у',
    'твцентр мир 24 рбк поток',
    'отр общественное телевидение m3u8',
    '5 канал петербург прямой эфир hls',
    
    # === НОВОСТНЫЕ КАНАЛЫ ===
    'россия 24 прямой эфир m3u8',
    'rtvi независимое телевидение stream',
    'euronews русский версия m3u8',
    'dw deutsche welle russian stream',
    'france24 russian hls',
    'bbc news russian service',
    'cnn international m3u8',
    'aljazeera english stream',
    'sky news live m3u8',
    'bloomberg tv stream',
    'cnbc international hls',
    'reuters tv live stream',
    
    # === ПЛАТНЫЕ ПЛАТФОРМЫ И ПРОВАЙДЕРЫ ===
    'забава винк ростелеком плейлист m3u',
    'wink rostelecom iptv m3u8',
    'ertelecom domru playlist',
    'megafon tv iptv streams',
    'beeline tv channels m3u8',
    'mts tv streaming playlist',
    'tele2 tv iptv links',
    'ntv plus online stream m3u8',
    'tricolor tv direct stream',
    'akado tv iptv playlist',
    'onlime tv channels m3u',
    
    # === СПОРТИВНЫЕ КАНАЛЫ ===
    'матч премьер прямой эфир m3u8',
    'матч футбол 1 2 3 stream hls',
    'матч арена онлайн m3u8',
    'матч боец прямой эфир',
    'матч страна stream',
    'eurosport russian hls',
    'sport24 live stream m3u8',
    
    # === РАЗВЛЕКАТЕЛЬНЫЕ КАНАЛЫ ===
    'тнт музыка прямой эфир m3u8',
    'муз тв онлайн stream',
    'ру тв прямой эфир hls',
    'bridge tv stream m3u8',
    'юмор тв онлайн',
    'комедия тв stream',
    
    # === ДЕТСКИЕ КАНАЛЫ ===
    'карусель прямой эфир m3u8',
    'кармелит тв детский канал',
    'мульт тв онлайн stream',
    'аниме тв россия hls',
    'disney channel russian m3u8',
    'nickelodeon russian stream',
    
    # === ПОЗНАВАТЕЛЬНЫЕ КАНАЛЫ ===
    'discovery channel russian m3u8',
    'national geographic russian hls',
    'history channel russia stream',
    'science 2.0 тв м3у8',
    'живая планета тв онлайн',
    'мое открытие тв stream',
    
    # === КИНОКАНАЛЫ ===
    'премьер тв прямой эфир m3u8',
    'кинопоиск тв stream hls',
    'амедиа тв премиум m3u8',
    'fox russian stream',
    'hbo russian version hls',
    
    # === РЕГИОНАЛЬНЫЕ КАНАЛЫ ===
    'москва 24 прямой эфир m3u8',
    'санкт петербург тв stream',
    'кубань тв краснодар hls',
    'дон 24 ростов на дону m3u8',
    'урал 1 екатеринбург тв',
    'сибирь тв новосибирск stream',
    
    # === УКРАИНСКИЕ КАНАЛЫ ===
    'украина 24 прямой эфир m3u8',
    '1+1 украина онлайн stream',
    'интер тв ukraina hls',
    'ictv киив stream m3u8',
    '5 канал украина прямой эфир',
    
    # === БЕЛОРУССКИЕ КАНАЛЫ ===
    'беларусь 1 прямой эфир m3u8',
    'онт минск онлайн stream',
    'столичное тв беларусь hls',
    
    # === КАЗАХСТАНСКИЕ КАНАЛЫ ===
    'хабар 24 казахстан m3u8',
    'казакстан тв астана stream',
    'ктк алматы прямой эфир',
    
    # === МЕЖДУНАРОДНЫЕ НА РУССКОМ ===
    'cgtn russian china tv m3u8',
    'rt documentary russian stream',
    'sputnik news tv hls',
    'tass tv direct stream',
    
    # === ТЕХНИЧЕСКИЕ ЗАПРОСЫ ===
    'live tv russia hls m3u8',
    'russian tv channels stream',
    'iptv free playlist working 2026',
    'm3u8 http live streaming russia',
    'hls ts segments tv channels',
]


class IPTVScanner:
    def __init__(self):
        self.found_streams: Dict[str, Dict] = {}
        self.session = None
        self.semaphore = asyncio.Semaphore(50)
        self.channel_history: Dict[str, Dict] = {}
        self.new_channels_count = 0

    async def init_session(self):
        timeout = aiohttp.ClientTimeout(total=15)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
        }
        self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)

    async def close_session(self):
        if self.session:
            await self.session.close()

    def log(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        print(log_msg)
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(log_msg + '\n')
        except Exception:
            pass

    def get_stream_hash(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    async def load_channel_history(self):
        """Загружает историю каналов для сохранения старых каналов"""
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    self.channel_history = json.load(f)
                self.log(f"📚 Загружена история {len(self.channel_history)} каналов")
            except Exception as e:
                self.log(f"⚠️ Не удалось загрузить историю: {e}")

    async def save_channel_history(self):
        """Сохраняет историю каналов"""
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.channel_history, f, ensure_ascii=False, indent=2)

    async def check_stream_availability(self, url: str) -> bool:
        """Проверка доступности потока (упрощенная для GitHub Actions)"""
        try:
            # Определяем доверенные CDN которые работают без прокси
            direct_domains = [
                'zabava-htlive.cdn.ngenix.net',
                'tvrain.tv', 'tvrain.akamaized.net',
                'd1vrcsh6f4z3z8.cloudfront.net',
                'cdn.tvrain.tv', 'hls.tvrain.tv'
            ]
            
            use_proxy = not any(domain in url for domain in direct_domains)
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
            }
            
            # Для GitHub Actions используем упрощенную проверку
            # просто проверяем что URL валидный
            if use_proxy:
                # С прокси не проверяем в GitHub Actions (требует настройки)
                return True
            else:
                # Для прямых CDN делаем быструю проверку
                try:
                    async with self.session.head(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                        return response.status in [200, 206, 301, 302]
                except Exception:
                    return True  # Разрешаем даже если не смогли проверить
                    
        except Exception:
            return True  # По умолчанию разрешаем

    async def check_and_add(self, url: str, source: str = "scan", name: str = None, group: str = "IPTV") -> bool:
        """Проверяет и добавляет канал, НЕ удаляя старые"""
        async with self.semaphore:
            try:
                # Пропускаем исключенный домен
                if EXCLUDED_DOMAIN in url.lower():
                    return False
                
                # Если канал уже есть - не добавляем повторно
                if url in self.found_streams:
                    return False
                
                channel_name = self.clean_channel_name(name or "Unknown")
                
                is_ru = any(kw in url.lower() for kw in RU_KEYWORDS) or \
                        any(kw in channel_name.lower() for kw in RU_KEYWORDS)
                
                # Для приоритетных источников и m3u-источников не проверяем доступность в GitHub Actions
                # чтобы не терять каналы из-за проблем с сетью
                if source not in ["priority", "m3u_source"]:
                    # Проверяем доступность только для веб-поиска
                    is_available = await self.check_stream_availability(url)
                    if not is_available:
                        return False
                
                # Добавляем канал (ограничение 30000)
                if len(self.found_streams) < 30000:
                    stream_hash = self.get_stream_hash(url)
                    
                    # НЕ блокируем добавление по истории - даем шанс каналу
                    # Вместо этого просто логируем если был помечен как dead
                    if stream_hash in self.channel_history:
                        old_info = self.channel_history[stream_hash]
                        if old_info.get('status') == 'dead':
                            # Все равно добавляем - вдруг канал ожил!
                            self.log(f"♻️ Канал вернулся из мертвых: {channel_name}")
                    
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
                
            except Exception as e:
                self.log(f"⚠️ Ошибка при проверке канала: {e}")
                return False

    async def fetch_m3u_from_source(self, url: str) -> List[Dict]:
        """Загружает каналы из m3u плейлиста"""
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

                    self.log(f"📄 Извлечено {len(channels)} каналов из {url[:60]}")
                    return channels
        except Exception as e:
            self.log(f"❌ Ошибка получения {url[:60]}: {e}")
        return []

    async def scan_m3u_sources(self):
        """Сканирует публичные m3u плейлисты"""
        self.log("🌐 Сканирование публичных IPTV плейлистов...")
        tasks = [self.fetch_m3u_from_source(source) for source in M3U_SOURCES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                for channel in result:
                    await self.check_and_add(channel['url'], source="m3u_source", 
                                           name=channel['name'], group=channel['group'])

    async def search_web(self):
        """Поиск IPTV потоков через поисковые системы"""
        self.log("🔍 Поиск по сайтам через поисковые системы...")
        
        # Расширенный поиск - используем все запросы для лучшего покрытия
        for query in SEARCH_QUERIES:  # Все запросы для максимального охвата
            try:
                search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}&num=10"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'text/html,application/xhtml+xml',
                }
                
                async with self.session.get(search_url, headers=headers, 
                                          timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        text = await response.text()
                        
                        # Извлекаем m3u8/m3u URL
                        m3u_pattern = r'https?[^\s"\'<>]+\.m3u8?[^\s"\'<>]*'
                        matches = re.findall(m3u_pattern, text, re.IGNORECASE)
                        
                        for match in matches[:20]:  # Максимум 20 URL из каждого запроса
                            clean_url = match.replace('&amp;', '&').replace('"', '')
                            if clean_url.startswith('http') and EXCLUDED_DOMAIN not in clean_url:
                                await self.check_and_add(clean_url, source="web_search")
                                
            except Exception as e:
                self.log(f"⚠️ Ошибка поиска: {e}")
            
            await asyncio.sleep(1)  # Пауза между запросами

    def clean_channel_name(self, name: str) -> str:
        """Очищает название канала от технических суффиксов"""
        if not name:
            return "Канал"
        
        cleaned = name
        cleaned = re.sub(r'\s*\(1080p\)', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*\(720p\)', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*\[Not 24/7\]\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*HD\s*', ' ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned if cleaned else "Канал"

    def generate_m3u(self) -> str:
        """Генерирует M3U плейлист с приоритетными каналами в начале"""
        m3u_content = "#EXTM3U\n"
        m3u_content += f"# Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        m3u_content += f"# Всего каналов: {len(self.found_streams)}\n"
        m3u_content += f"# Новых за сессию: {self.new_channels_count}\n"
        m3u_content += "# LiveM3U Scanner - автоматическое обновление\n"
        m3u_content += "# ПРИОРИТЕТ: Канал Дождь и важные каналы добавлены в начало!\n\n"

        # Сначала приоритетные каналы (Дождь и другие важные)
        priority_streams = [(url, info) for url, info in self.found_streams.items() 
                           if info.get('source') == 'priority']
        
        # Затем остальные российские каналы
        ru_streams = [(url, info) for url, info in self.found_streams.items() 
                     if info.get('country') == 'RU' and info.get('source') != 'priority']
        
        # Затем международные каналы
        int_streams = [(url, info) for url, info in self.found_streams.items() 
                      if info.get('country') != 'RU' and info.get('source') != 'priority']

        # Приоритетные каналы идут первыми - ВСЕ С ПРОКСИ
        for url, info in priority_streams:
            name = info.get('name', 'Channel')
            group = info.get('group', 'IPTV')
            
            # ВСЕ каналы включая приоритетные идут через прокси
            parsed = urllib.parse.urlparse(url)
            stream_url = f"{PROXY_BASE}{parsed.netloc}{parsed.path}"
            if parsed.query:
                stream_url += '?' + parsed.query
            
            m3u_content += f'#EXTINF:-1 tvg-name="{name}" group-title="{group}",{name} ⭐\n'
            m3u_content += f'{stream_url}\n\n'

        # Затем российские каналы
        for url, info in ru_streams:
            name = info.get('name', 'Channel')
            group = info.get('group', 'IPTV')
            
            # Определяем нужен ли прокси
            direct_domains = ['zabava-htlive.cdn.ngenix.net', 'tvrain.tv', 
                            'tvrain.akamaized.net', 'cloudfront.net']
            use_proxy = not any(domain in url for domain in direct_domains)
            
            if use_proxy:
                parsed = urllib.parse.urlparse(url)
                stream_url = f"{PROXY_BASE}{parsed.netloc}{parsed.path}"
                if parsed.query:
                    stream_url += '?' + parsed.query
            else:
                stream_url = url
            
            m3u_content += f'#EXTINF:-1 tvg-name="{name}" group-title="{group}",{name}\n'
            m3u_content += f'{stream_url}\n\n'

        # Затем международные каналы
        for url, info in int_streams:
            name = info.get('name', 'Channel')
            group = info.get('group', 'IPTV')
            
            # Определяем нужен ли прокси
            direct_domains = ['zabava-htlive.cdn.ngenix.net', 'tvrain.tv', 
                            'tvrain.akamaized.net', 'cloudfront.net']
            use_proxy = not any(domain in url for domain in direct_domains)
            
            if use_proxy:
                parsed = urllib.parse.urlparse(url)
                stream_url = f"{PROXY_BASE}{parsed.netloc}{parsed.path}"
                if parsed.query:
                    stream_url += '?' + parsed.query
            else:
                stream_url = url
            
            m3u_content += f'#EXTINF:-1 tvg-name="{name}" group-title="{group}",{name}\n'
            m3u_content += f'{stream_url}\n\n'

        return m3u_content

    async def load_existing_streams(self):
        """Загружает ранее найденные потоки для сохранения"""
        if FOUND_STREAMS_FILE.exists():
            try:
                with open(FOUND_STREAMS_FILE, 'r', encoding='utf-8') as f:
                    loaded_streams = json.load(f)
                
                # Очищаем названия при загрузке
                for url, info in loaded_streams.items():
                    if 'name' in info:
                        info['name'] = self.clean_channel_name(info['name'])
                    self.found_streams[url] = info
                
                self.log(f"📂 Загружено {len(self.found_streams)} ранее найденных потоков")
            except Exception as e:
                self.log(f"⚠️ Не удалось загрузить потоки: {e}")

    async def save_streams(self):
        """Сохраняет найденные потоки"""
        with open(FOUND_STREAMS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.found_streams, f, ensure_ascii=False, indent=2)
        self.log(f"💾 Сохранено {len(self.found_streams)} потоков")

    async def split_into_thematic_playlists(self):
        """Разделяет плейлист на тематические категории"""
        try:
            playlist_path = PLAYLIST_FILE
            if not playlist_path.exists():
                return
                
            with open(playlist_path, 'r', encoding='utf-8') as f:
                content = f.read()

            entries = re.split(r'(?=#EXTINF)', content)
            groups = {}
            header = "#EXTM3U\n"

            for entry in entries:
                if not entry.strip():
                    continue
                if entry.startswith('#EXTM3U'):
                    header = entry
                    continue

                match = re.search(r'group-title="([^"]*)"', entry)
                if match:
                    group_name = match.group(1)
                    if group_name not in groups:
                        groups[group_name] = []
                    groups[group_name].append(entry)
                else:
                    if 'No Group' not in groups:
                        groups['No Group'] = []
                    groups['No Group'].append(entry)

            output_dir = DATA_DIR / "playlists"
            output_dir.mkdir(exist_ok=True)

            for group_name, channels in groups.items():
                if not channels:
                    continue

                safe_name = re.sub(r'[^\w\s\u0400-\u04FF]', '_', group_name).strip()
                safe_name = re.sub(r'\s+', '_', safe_name)
                filename = f"{safe_name}.m3u"
                filepath = output_dir / filename
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(header)
                    f.write(f"# Категория: {group_name}\n")
                    f.write(f"# Каналов: {len(channels)}\n")
                    f.write(f"# Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    for channel in channels:
                        f.write(channel)

            self.log(f"✅ Создано {len(groups)} тематических плейлистов")

        except Exception as e:
            self.log(f"❌ Ошибка создания тематических плейлистов: {e}")

    async def add_priority_channels(self):
        """Добавляет приоритетные каналы (Дождь и другие важные) в начало плейлиста"""
        self.log("⭐ Добавление приоритетных каналов (Дождь и др.)...")
        for channel in PRIORITY_CHANNELS:
            await self.check_and_add(
                channel['url'], 
                source="priority", 
                name=channel['name'], 
                group=channel['group']
            )
        self.log(f"✅ Добавлено {len(PRIORITY_CHANNELS)} приоритетных каналов")

    async def run_scan(self):
        """Основной метод сканирования"""
        await self.init_session()

        self.log("🚀 Запуск LiveM3U Scanner...")
        self.log("🌐 Поиск каналов на сайтах (не YouTube)!")
        self.log(f"🔗 Прокси: {PROXY_HOST}")
        self.log("🔄 Режим: ДОБАВЛЕНИЕ новых каналов (старые не удаляются)")

        # Загружаем историю и существующие потоки
        await self.load_channel_history()
        await self.load_existing_streams()
        
        old_count = len(self.found_streams)
        self.new_channels_count = 0

        # 0. Сначала добавляем приоритетные каналы (Дождь и другие важные)
        await self.add_priority_channels()

        # 1. Сканирование m3u источников
        await self.scan_m3u_sources()

        # 2. Поиск по сайтам
        await self.search_web()

        self.log(f"✅ Найдено потоков: {len(self.found_streams)}")
        self.log(f"🆕 Добавлено новых каналов: {self.new_channels_count}")
        self.log(f"📊 Всего каналов в плейлисте: {len(self.found_streams)}")

        # Сохраняем потоки
        await self.save_streams()
        await self.save_channel_history()

        # Генерируем плейлист
        m3u_content = self.generate_m3u()
        DATA_DIR.mkdir(exist_ok=True)
        with open(PLAYLIST_FILE, 'w', encoding='utf-8') as f:
            f.write(m3u_content)

        self.log(f"📺 Плейлист сохранён: {PLAYLIST_FILE}")
        
        # Создаем тематические плейлисты
        await self.split_into_thematic_playlists()

        await self.close_session()


async def main():
    """Точка входа"""
    DATA_DIR.mkdir(exist_ok=True)
    
    scanner = IPTVScanner()
    await scanner.run_scan()
    
    print("\n" + "="*60)
    print("✅ Сканирование завершено успешно!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
