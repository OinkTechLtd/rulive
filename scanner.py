#!/usr/bin/env python3
"""
LiveM3U - Поисковой робот IPTV каналов (ULTIMATE VERSION)
Сканер для GitHub Actions - обновляет плейлисты каждые 30 минут
Ищет каналы на сайтах, парсит m3u плейлисты, добавляет EPG метаданные
НЕ удаляет старые каналы, только добавляет новые рабочие
ЦЕЛЬ: 150000+ рабочих каналов со всего интернета
"""

import asyncio
import aiohttp
import re
import json
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Set, Optional
import hashlib
import os
import random
from collections import defaultdict

# Конфигурация
DATA_DIR = Path("data")
PLAYLIST_FILE = DATA_DIR / "playlist.m3u"
FOUND_STREAMS_FILE = DATA_DIR / "found_streams.json"
HISTORY_FILE = DATA_DIR / "channel_history.json"
EPG_FILE = DATA_DIR / "epg_data.json"
LOG_FILE = DATA_DIR / "search.log"

# Таймауты HTTP и прогресс
HTTP_TIMEOUT_TOTAL = 25
HTTP_TIMEOUT_CONNECT = 10
HTTP_TIMEOUT_SOCK_CONNECT = 10
HTTP_TIMEOUT_SOCK_READ = 15
REQUEST_TIMEOUT_SHORT = 8
REQUEST_TIMEOUT_MEDIUM = 15
REQUEST_TIMEOUT_LONG = 25
SOURCE_PROGRESS_EVERY = 10
CHANNEL_PROGRESS_EVERY = 1000

# Прокси настройки из environment
PROXY_HOST = os.environ.get("PROXY_HOST", "secure-272717.tatnet.app")
PROXY_PORT = os.environ.get("PROXY_PORT", "8080")
PROXY_BASE = f"https://{PROXY_HOST}/"

# Исключаем этот домен из плейлистов
EXCLUDED_DOMAIN = "zabava-hlive.ngenix.net"

# Домены которые работают без прокси (только zabava-hlive.ngenix.net)
DIRECT_DOMAINS = [
    'zabava-hlive.ngenix.net',
]

# Домены которые НЕ требуют прокси (прямые CDN и рабочие сайты)
NO_PROXY_DOMAINS = [
    'zabava-hlive.ngenix.net',
    'iptv-org.github.io',
    'raw.githubusercontent.com',
    'cdn.jsdelivr.net',
    'cdn.statically.io',
    'raw.githack.com',
    'github.com',
    'render.com',
    'onrender.com',
]

# Максимальное количество каналов - УЛЬТИМАТИВНЫЙ ЛИМИТ
MAX_CHANNELS = 200000000

# EPG источники
EPG_SOURCES = [
    "https://iptv-org.github.io/epg/guides/ru.xml",
    "https://iptv-org.github.io/epg/guides/en.xml",
    "https://iptv-org.github.io/epg/guides/de.xml",
    "https://iptv-org.github.io/epg/guides/fr.xml",
    "https://iptv-org.github.io/epg/guides/es.xml",
    "https://iptv-org.github.io/epg/guides/it.xml",
    "https://raw.githubusercontent.com/tv-guides/epg/master/epg.xml",
]

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
    'rtl', 'pro7', 'tf1', 'm6', 'channel 4', 'itv',
    # === ДОПОЛНИТЕЛЬНЫЕ КЛЮЧЕВЫЕ СЛОВА ДЛЯ ПОИСКА ===
    'iptv', 'm3u', 'm3u8', 'hls', 'stream', 'live tv',
    'телеканал', 'тв', 'эфир', 'прямой эфир',
    'hd', 'fhd', 'uhd', '4k', 'online', 'онлайн'
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

# Источники m3u плейлистов для сканирования - УЛЬТИМАТИВНЫЙ СПИСОК (50% GitHub + 50% другие сайты)
M3U_SOURCES = [
    # === ОСНОВНЫЕ РАБОЧИЕ ИСТОЧНИКИ IPTV-ORG (GitHub) ===
    'https://iptv-org.github.io/iptv/countries/ru.m3u',
    'https://iptv-org.github.io/iptv/countries/ua.m3u',
    'https://iptv-org.github.io/iptv/countries/by.m3u',
    'https://iptv-org.github.io/iptv/countries/kz.m3u',
    'https://iptv-org.github.io/iptv/countries/us.m3u',
    'https://iptv-org.github.io/iptv/countries/gb.m3u',
    'https://iptv-org.github.io/iptv/countries/de.m3u',
    'https://iptv-org.github.io/iptv/countries/fr.m3u',
    'https://iptv-org.github.io/iptv/countries/es.m3u',
    'https://iptv-org.github.io/iptv/countries/it.m3u',
    'https://iptv-org.github.io/iptv/countries/jp.m3u',
    'https://iptv-org.github.io/iptv/countries/cn.m3u',
    'https://iptv-org.github.io/iptv/countries/in.m3u',
    'https://iptv-org.github.io/iptv/countries/tr.m3u',
    'https://iptv-org.github.io/iptv/countries/br.m3u',
    'https://iptv-org.github.io/iptv/countries/ar.m3u',
    'https://iptv-org.github.io/iptv/countries/mx.m3u',
    'https://iptv-org.github.io/iptv/countries/ca.m3u',
    'https://iptv-org.github.io/iptv/countries/au.m3u',
    'https://iptv-org.github.io/iptv/countries/nz.m3u',
    'https://iptv-org.github.io/iptv/languages/rus.m3u',
    'https://iptv-org.github.io/iptv/languages/eng.m3u',
    'https://iptv-org.github.io/iptv/languages/spa.m3u',
    'https://iptv-org.github.io/iptv/languages/deu.m3u',
    'https://iptv-org.github.io/iptv/languages/fra.m3u',
    'https://iptv-org.github.io/iptv/languages/ita.m3u',
    'https://iptv-org.github.io/iptv/languages/por.m3u',
    'https://iptv-org.github.io/iptv/languages/jpn.m3u',
    'https://iptv-org.github.io/iptv/languages/zho.m3u',
    'https://iptv-org.github.io/iptv/languages/ara.m3u',
    # === КАТЕГОРИИ IPTV-ORG ===
    'https://iptv-org.github.io/iptv/categories/news.m3u',
    'https://iptv-org.github.io/iptv/categories/movies.m3u',
    'https://iptv-org.github.io/iptv/categories/sports.m3u',
    'https://iptv-org.github.io/iptv/categories/kids.m3u',
    'https://iptv-org.github.io/iptv/categories/music.m3u',
    'https://iptv-org.github.io/iptv/categories/documentary.m3u',
    'https://iptv-org.github.io/iptv/categories/entertainment.m3u',
    'https://iptv-org.github.io/iptv/categories/science.m3u',
    'https://iptv-org.github.io/iptv/categories/religion.m3u',
    'https://iptv-org.github.io/iptv/categories/outdoor.m3u',
    'https://iptv-org.github.io/iptv/categories/automotive.m3u',
    'https://iptv-org.github.io/iptv/categories/travel.m3u',
    'https://iptv-org.github.io/iptv/categories/weather.m3u',
    'https://iptv-org.github.io/iptv/categories/business.m3u',
    'https://iptv-org.github.io/iptv/categories/culture.m3u',
    'https://iptv-org.github.io/iptv/categories/fashion.m3u',
    'https://iptv-org.github.io/iptv/categories/food.m3u',
    'https://iptv-org.github.io/iptv/categories/series.m3u',
    'https://iptv-org.github.io/iptv/categories/lifestyle.m3u',
    'https://iptv-org.github.io/iptv/categories/education.m3u',
    # === ВСЕ КАНАЛЫ МИРА IPTV-ORG ===
    'https://iptv-org.github.io/iptv/index.m3u',
    
    # === РОССИЙСКИЕ IPTV ПЛЕЙЛИСТЫ (GitHub) ===
    'https://raw.githubusercontent.com/AleksandrChtol/iptv/main/iptv.m3u',
    'https://raw.githubusercontent.com/free-TV/iptv/master/playlist.m3u8',
    'https://raw.githubusercontent.com/CrocoUser/zabava-project/refs/heads/main/zabava-full.m3u',
    'https://raw.githubusercontent.com/CrocoUser/zabava-project/refs/heads/main/zabava-reg.m3u',
    'https://raw.githubusercontent.com/jnk0le/iptv-ru/main/playlist.m3u',
    'https://raw.githubusercontent.com/Evmenkov/iptv/main/iptv.m3u',
    'https://raw.githubusercontent.com/vasilyguk/iptv/main/playlist.m3u',
    'https://raw.githubusercontent.com/QuickLink/iptv/main/playlist.m3u',
    'https://raw.githubusercontent.com/black-bell/iptv/main/ru.m3u',
    'https://raw.githubusercontent.com/nickvsn/iptv/main/iptv.m3u',
    'https://raw.githubusercontent.com/AndreyKuznetsov/iptv/main/playlist.m3u',
    'https://raw.githubusercontent.com/postpos/iptv/main/playlist.m3u',
    'https://raw.githubusercontent.com/Krasnikoff/iptv/main/playlist.m3u',
    'https://raw.githubusercontent.com/Siberman/iptv/main/playlist.m3u',
    'https://raw.githubusercontent.com/AlexxxH/iptv/main/playlist.m3u',
    'https://raw.githubusercontent.com/vitiko/IPTV/main/playlist.m3u',
    'https://raw.githubusercontent.com/laap/iptv/master/ru.m3u',
    'https://raw.githubusercontent.com/freearhey/iptv/master/ru.m3u',
    'https://raw.githubusercontent.com/jnk0le/iptv-ru/main/filtered.m3u',
    'https://raw.githubusercontent.com/veleek/iptv3/main/iptv.m3u',
    'https://raw.githubusercontent.com/evgenich/iptv/main/playlist.m3u',
    'https://raw.githubusercontent.com/DimasikIT/iptv/main/playlist.m3u',
    'https://raw.githubusercontent.com/DenisKor/iptv/main/playlist.m3u',
    'https://raw.githubusercontent.com/IgorKopylov/iptv/main/playlist.m3u',
    'https://raw.githubusercontent.com/PlayListX/iptv/main/ru.m3u',
    
    # === МЕЖДУНАРОДНЫЕ ПЛЕЙЛИСТЫ (GitHub) ===
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/us.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/gb.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/de.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/fr.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/es.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/it.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/tr.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/br.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/ar.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/cn.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/jp.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/kr.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/in.m3u',
    
    # === СПОРТИВНЫЕ КАНАЛЫ (GitHub) ===
    'https://raw.githubusercontent.com/StreamHub-Eurosport/Eurosport/main/Eurosport.m3u',
    'https://raw.githubusercontent.com/StreamHub-SkySports/SkySports/main/SkySports.m3u',
    'https://raw.githubusercontent.com/StreamHub-BeIN/BeIN-Sports/main/BeIN-Sports.m3u',
    
    # === ФИЛЬМЫ И СЕРИАЛЫ (GitHub) ===
    'https://raw.githubusercontent.com/Liveloom/iptv-channels/main/playlist.m3u',
    'https://raw.githubusercontent.com/MoH-MoH/iptv-channels/master/ALL.m3u',
    
    # === НЕ GITHUB ИСТОЧНИКИ - ПРЯМЫЕ САЙТЫ С M3U ===
    # Европейские плейлисты
    'https://www.lyngsat-address.com/getfile.php?filename=stream&language=all&country=all&system=all&format=m3u',
    'https://raw.githubusercontent.com/iptv-org/epg/master/sites.xml',
    
    # Американские источники
    'https://m3u.poledia.org/usa.m3u',
    'https://m3u.poledia.org/uk.m3u',
    'https://m3u.poledia.org/germany.m3u',
    'https://m3u.poledia.org/france.m3u',
    'https://m3u.poledia.org/spain.m3u',
    'https://m3u.poledia.org/italy.m3u',
    
    # Азиатские источники
    'https://iptv-org-abroad.onrender.com/countries/asia/in.m3u',
    'https://iptv-org-abroad.onrender.com/countries/asia/jp.m3u',
    'https://iptv-org-abroad.onrender.com/countries/asia/kr.m3u',
    'https://iptv-org-abroad.onrender.com/countries/asia/cn.m3u',
    
    # Латинская Америка
    'https://raw.githubusercontent.com/luisbeltran1/TV/main/lista.m3u',
    'https://raw.githubusercontent.com/AlfredoHR/Lista-IPTV-Espana/main/lista.m3u',
    
    # Африканские и ближневосточные
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/ae.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/za.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/eg.m3u',
    
    # Дополнительные российские источники с других хостингов
    'https://cdn.jsdelivr.net/gh/iptv-org/iptv@master/iptv.countries.ru.m3u',
    'https://cdn.statically.io/gh/iptv-org/iptv@master/iptv.languages.rus.m3u',
    
    # Тематические плейлисты
    'https://raw.githubusercontent.com/FreeIPTV/channels/main/ru.m3u',
    'https://raw.githubusercontent.com/tv-box/ec/main/live.m3u',
    'https://raw.githubusercontent.com/xiaomi128/iptv/main/live.txt',
    
    # === НОВЫЕ ИСТОЧНИКИ С САЙТОВ ПОДДЕРЖИВАЮЩИХ M3U8 (НЕ GITHUB) ===
    # Прямые ссылки с сайтов которые отдают m3u8 плейлисты
    'https://www.lyngsat-address.com/getfile.php?filename=stream&language=all&country=all&system=all&format=m3u',
    'https://m3u.poledia.org/all.m3u',
    'https://m3u.poledia.org/world.m3u',
    'https://m3u.poledia.org/europe.m3u',
    'https://m3u.poledia.org/asia.m3u',
    'https://m3u.poledia.org/africa.m3u',
    'https://m3u.poledia.org/south-america.m3u',
    'https://m3u.poledia.org/north-america.m3u',
    'https://m3u.poledia.org/oceania.m3u',
    
    # Сайты с прямыми m3u8 потоками
    'https://iptv-org.github.io/iptv/index.m3u',
    'https://iptv-org.github.io/iptv/index.country.m3u',
    'https://iptv-org.github.io/iptv/index.language.m3u',
    'https://iptv-org.github.io/iptv/index.category.m3u',
    
    # Дополнительные агрегаторы IPTV
    'https://github.com/iptv-org/iptv/raw/master/iptv.m3u',
    'https://cdn.jsdelivr.net/gh/iptv-org/iptv@master/iptv.m3u',
    'https://cdn.statically.io/gh/iptv-org/iptv@master/iptv.m3u',
    'https://raw.githack.com/iptv-org/iptv/master/iptv.m3u',
    
    # Региональные плейлисты со всего мира
    'https://iptv-org-abroad.onrender.com/countries/all.m3u',
    'https://iptv-org-abroad.onrender.com/categories/all.m3u',
    'https://iptv-org-abroad.onrender.com/languages/all.m3u',
    
    # Европейские IPTV источники
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/eu.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/nl.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/pl.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/se.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/no.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/dk.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/fi.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/gr.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/pt.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/at.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/ch.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/be.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/ie.m3u',
    
    # Азиатско-тихоокеанский регион
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/th.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/vn.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/ph.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/id.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/my.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/sg.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/hk.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/tw.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/pk.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/bd.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/lk.m3u',
    
    # Ближний Восток и Африка
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/sa.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/ir.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/iq.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/il.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/tr.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/ng.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/ke.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/gh.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/ma.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/dz.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/tn.m3u',
    
    # Постсоветское пространство
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/az.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/am.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/ge.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/md.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/lt.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/lv.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/ee.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/uz.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/tm.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/kg.m3u',
    'https://raw.githubusercontent.com/iptv-org/iptv/master/playlists/tj.m3u',
    
    # Все категории каналов
    'https://iptv-org.github.io/iptv/categories/classic.m3u',
    'https://iptv-org.github.io/iptv/categories/comedy.m3u',
    'https://iptv-org.github.io/iptv/categories/cooking.m3u',
    'https://iptv-org.github.io/iptv/categories/criminal.m3u',
    'https://iptv-org.github.io/iptv/categories/family.m3u',
    'https://iptv-org.github.io/iptv/categories/general.m3u',
    'https://iptv-org.github.io/iptv/categories/legislative.m3u',
    'https://iptv-org.github.io/iptv/categories/movies.m3u',
    'https://iptv-org.github.io/iptv/categories/nature.m3u',
    'https://iptv-org.github.io/iptv/categories/outdoor.m3u',
    'https://iptv-org.github.io/iptv/categories/politics.m3u',
    'https://iptv-org.github.io/iptv/categories/regional.m3u',
    'https://iptv-org.github.io/iptv/categories/research.m3u',
    'https://iptv-org.github.io/iptv/categories/shopping.m3u',
    'https://iptv-org.github.io/iptv/categories/sports.m3u',
    'https://iptv-org.github.io/iptv/categories/tech.m3u',
    'https://iptv-org.github.io/iptv/categories/webcam.m3u',
    'https://iptv-org.github.io/iptv/categories/xxx.m3u',
    
    # Все языки мира
    'https://iptv-org.github.io/iptv/languages/afr.m3u',
    'https://iptv-org.github.io/iptv/languages/amh.m3u',
    'https://iptv-org.github.io/iptv/languages/ara.m3u',
    'https://iptv-org.github.io/iptv/languages/aze.m3u',
    'https://iptv-org.github.io/iptv/languages/bel.m3u',
    'https://iptv-org.github.io/iptv/languages/ben.m3u',
    'https://iptv-org.github.io/iptv/languages/bul.m3u',
    'https://iptv-org.github.io/iptv/languages/cat.m3u',
    'https://iptv-org.github.io/iptv/languages/ces.m3u',
    'https://iptv-org.github.io/iptv/languages/chr.m3u',
    'https://iptv-org.github.io/iptv/languages/cym.m3u',
    'https://iptv-org.github.io/iptv/languages/dan.m3u',
    'https://iptv-org.github.io/iptv/languages/ell.m3u',
    'https://iptv-org.github.io/iptv/languages/epo.m3u',
    'https://iptv-org.github.io/iptv/languages/est.m3u',
    'https://iptv-org.github.io/iptv/languages/eus.m3u',
    'https://iptv-org.github.io/iptv/languages/faa.m3u',
    'https://iptv-org.github.io/iptv/languages/fin.m3u',
    'https://iptv-org.github.io/iptv/languages/fil.m3u',
    'https://iptv-org.github.io/iptv/languages/guj.m3u',
    'https://iptv-org.github.io/iptv/languages/heb.m3u',
    'https://iptv-org.github.io/iptv/languages/hin.m3u',
    'https://iptv-org.github.io/iptv/languages/hrv.m3u',
    'https://iptv-org.github.io/iptv/languages/hun.m3u',
    'https://iptv-org.github.io/iptv/languages/hye.m3u',
    'https://iptv-org.github.io/iptv/languages/ind.m3u',
    'https://iptv-org.github.io/iptv/languages/isl.m3u',
    'https://iptv-org.github.io/iptv/languages/kat.m3u',
    'https://iptv-org.github.io/iptv/languages/kaz.m3u',
    'https://iptv-org.github.io/iptv/languages/khm.m3u',
    'https://iptv-org.github.io/iptv/languages/kor.m3u',
    'https://iptv-org.github.io/iptv/languages/kur.m3u',
    'https://iptv-org.github.io/iptv/languages/lao.m3u',
    'https://iptv-org.github.io/iptv/languages/lat.m3u',
    'https://iptv-org.github.io/iptv/languages/lin.m3u',
    'https://iptv-org.github.io/iptv/languages/lit.m3u',
    'https://iptv-org.github.io/iptv/languages/mkd.m3u',
    'https://iptv-org.github.io/iptv/languages/mlg.m3u',
    'https://iptv-org.github.io/iptv/languages/mon.m3u',
    'https://iptv-org.github.io/iptv/languages/msa.m3u',
    'https://iptv-org.github.io/iptv/languages/mya.m3u',
    'https://iptv-org.github.io/iptv/languages/nep.m3u',
    'https://iptv-org.github.io/iptv/languages/nld.m3u',
    'https://iptv-org.github.io/iptv/languages/nob.m3u',
    'https://iptv-org.github.io/iptv/languages/ori.m3u',
    'https://iptv-org.github.io/iptv/languages/pan.m3u',
    'https://iptv-org.github.io/iptv/languages/pes.m3u',
    'https://iptv-org.github.io/iptv/languages/pol.m3u',
    'https://iptv-org.github.io/iptv/languages/pus.m3u',
    'https://iptv-org.github.io/iptv/languages/ron.m3u',
    'https://iptv-org.github.io/iptv/languages/rus.m3u',
    'https://iptv-org.github.io/iptv/languages/slk.m3u',
    'https://iptv-org.github.io/iptv/languages/slv.m3u',
    'https://iptv-org.github.io/iptv/languages/som.m3u',
    'https://iptv-org.github.io/iptv/languages/sqi.m3u',
    'https://iptv-org.github.io/iptv/languages/srp.m3u',
    'https://iptv-org.github.io/iptv/languages/swa.m3u',
    'https://iptv-org.github.io/iptv/languages/swe.m3u',
    'https://iptv-org.github.io/iptv/languages/tam.m3u',
    'https://iptv-org.github.io/iptv/languages/tel.m3u',
    'https://iptv-org.github.io/iptv/languages/tgk.m3u',
    'https://iptv-org.github.io/iptv/languages/tha.m3u',
    'https://iptv-org.github.io/iptv/languages/tir.m3u',
    'https://iptv-org.github.io/iptv/languages/tuk.m3u',
    'https://iptv-org.github.io/iptv/languages/tur.m3u',
    'https://iptv-org.github.io/iptv/languages/ukr.m3u',
    'https://iptv-org.github.io/iptv/languages/urd.m3u',
    'https://iptv-org.github.io/iptv/languages/uzb.m3u',
    'https://iptv-org.github.io/iptv/languages/vie.m3u',
    'https://iptv-org.github.io/iptv/languages/yid.m3u',
    'https://iptv-org.github.io/iptv/languages/yor.m3u',
    'https://iptv-org.github.io/iptv/languages/zho.m3u',
    'https://iptv-org.github.io/iptv/languages/zul.m3u',
]

# Поисковые запросы для поиска потоков на сайтах - МАКСИМАЛЬНО РАСШИРЕННЫЙ СПИСОК
# Прямые URL сайтов для парсинга (вместо Google поиска который блокируется)
DIRECT_SITES = [
    # Российские IPTV сайты и плейлисты
    'https://iptv-ru.com/playlist.m3u',
    'https://raw.githubusercontent.com/AleksandrChtol/iptv/main/iptv.m3u',
    'https://iptv.dreamteam.digital/playlist.m3u',
    'https://raw.githubusercontent.com/free-TV/iptv/master/playlist.m3u8',
    'https://raw.githubusercontent.com/jnk0le/iptv-ru/main/playlist.m3u',
    'https://raw.githubusercontent.com/Evmenkov/iptv/main/iptv.m3u',
    'https://raw.githubusercontent.com/vasilyguk/iptv/main/playlist.m3u',
    
    # Зарубежные агрегаторы
    'https://iptv-org.github.io/iptv/countries/ru.m3u',
    'https://iptv-org.github.io/iptv/languages/rus.m3u',
    'https://iptv-org.github.io/iptv/categories/news.m3u',
    'https://iptv-org.github.io/iptv/categories/movies.m3u',
    'https://iptv-org.github.io/iptv/categories/sports.m3u',
    'https://iptv-org.github.io/iptv/index.m3u',
    
    # Дополнительные источники m3u плейлистов
    'https://m3u.poledia.org/all.m3u',
    'https://m3u.poledia.org/usa.m3u',
    'https://m3u.poledia.org/uk.m3u',
    'https://m3u.poledia.org/germany.m3u',
    'https://m3u.poledia.org/france.m3u',
    'https://m3u.poledia.org/spain.m3u',
    'https://m3u.poledia.org/italy.m3u',
    'https://m3u.poledia.org/world.m3u',
    'https://m3u.poledia.org/europe.m3u',
    
    # CDN и зеркала iptv-org
    'https://cdn.jsdelivr.net/gh/iptv-org/iptv@master/iptv.countries.ru.m3u',
    'https://cdn.statically.io/gh/iptv-org/iptv@master/iptv.languages.rus.m3u',
    'https://raw.githack.com/iptv-org/iptv/master/iptv.m3u',
    
    # Render и другие хостинги
    'https://iptv-org-abroad.onrender.com/countries/all.m3u',
    'https://iptv-org-abroad.onrender.com/categories/all.m3u',
    'https://iptv-org-abroad.onrender.com/languages/all.m3u',
    
    # Тематические плейлисты
    'https://raw.githubusercontent.com/FreeIPTV/channels/main/ru.m3u',
    'https://raw.githubusercontent.com/tv-box/ec/main/live.m3u',
]

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
    'eurosport 1 live stream m3u8',
    'eurosport 2 direct hls',
    'eurosport 3 4 5 stream',
    'sport24 live stream m3u8',
    'bein sports russian m3u8',
    'sky sports main event hls',
    'dazn live stream russia',
    
    # === РЕГИОНАЛЬНЫЕ КАНАЛЫ SPB ===
    'спб тв прямой эфир m3u8',
    'санкт петербург тв stream',
    '7 канал спб прямой эфир',
    'spb 7 tv live hls',
    'петербург 5 канал m3u8',
    'спб 24 новости stream',
    'карповка спб тв hls',
    'тв санкт петербург m3u8',
    
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

# Популярные бренды/каналы для приоритетного интернет-поиска
POPULAR_CHANNEL_QUERIES = [
    "Первый канал", "Россия 1", "Россия 24", "НТВ", "ТНТ", "СТС",
    "Матч ТВ", "РЕН ТВ", "Пятый канал", "ТВ Центр", "Карусель",
    "МИР 24", "ОТР", "RTVI", "Евроньюс", "BBC News", "CNN", "Sky News",
    "Discovery", "National Geographic", "History Channel",
    "Eurosport 1", "Eurosport 2", "beIN Sports", "ESPN", "DAZN",
]


class IPTVScanner:
    def __init__(self):
        self.found_streams: Dict[str, Dict] = {}
        self.session = None
        self.semaphore = asyncio.Semaphore(50)
        self.channel_history: Dict[str, Dict] = {}
        self.new_channels_count = 0
        self.name_to_urls: Dict[str, Set[str]] = defaultdict(set)
        self.replaced_dead_count = 0
        self.fast_scan = os.environ.get("FAST_SCAN", "0") == "1"
        # Быстрый режим для GitHub Actions: без пропуска этапов, только с урезанием объема
        self.m3u_source_limit = 35 if self.fast_scan else len(M3U_SOURCES)
        self.dynamic_source_limit = 30 if self.fast_scan else 200
        self.search_query_limit = 10 if self.fast_scan else None
        self.validate_sample_limit = 1200 if self.fast_scan else 15000
        self.direct_sites_limit = 8 if self.fast_scan else None
        self.iptv_sites_limit = 4 if self.fast_scan else None

    async def init_session(self):
        timeout = aiohttp.ClientTimeout(
            total=HTTP_TIMEOUT_TOTAL,
            connect=HTTP_TIMEOUT_CONNECT,
            sock_connect=HTTP_TIMEOUT_SOCK_CONNECT,
            sock_read=HTTP_TIMEOUT_SOCK_READ,
        )
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        }
        # Используем TCPConnector с увеличенным пулом соединений для параллельных запросов
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=20, ttl_dns_cache=300, use_dns_cache=True)
        self.session = aiohttp.ClientSession(timeout=timeout, headers=headers, connector=connector)

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
        """Проверка доступности потока с поддержкой прокси для GitHub Actions"""
        try:
            # Используем расширенную логику: DIRECT_DOMAINS и NO_PROXY_DOMAINS без прокси
            use_proxy = not any(domain in url for domain in DIRECT_DOMAINS) and \
                       not any(domain in url for domain in NO_PROXY_DOMAINS)
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
            }
            
            # Для GitHub Actions используем упрощенную проверку
            # просто проверяем что URL валидный - НЕ УДАЛЯЕМ КАНАЛЫ!
            if use_proxy:
                # С прокси не проверяем в GitHub Actions (требует настройки)
                # ВАЖНО: Возвращаем True чтобы не потерять каналы из плейлистов
                return True
            else:
                # Для прямых CDN делаем быструю проверку
                try:
                    async with self.session.head(url, headers=headers, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SHORT)) as response:
                        return response.status in [200, 206, 301, 302]
                except Exception:
                    return True  # Разрешаем даже если не смогли проверить - НЕ УДАЛЯТЬ!
                    
        except Exception:
            return True  # По умолчанию разрешаем - ГЛАВНЫЙ ПРИНЦИП: НЕ ТЕРЯТЬ КАНАЛЫ!

    async def validate_existing_streams(self, sample_limit: int = 15000):
        """Проверяет существующие потоки и помечает недоступные как dead (без удаления)."""
        self.log("🩺 Проверка актуальности существующих потоков...")
        urls = list(self.found_streams.keys())[:sample_limit]
        checked = 0
        dead = 0
        for url in urls:
            checked += 1
            is_ok = await self.check_stream_availability(url)
            info = self.found_streams.get(url, {})
            stream_hash = info.get("hash") or self.get_stream_hash(url)
            hist = self.channel_history.get(stream_hash, {})
            hist["url"] = url
            hist["name"] = info.get("name", "Unknown")
            hist["last_seen"] = datetime.now().isoformat()
            hist["country"] = info.get("country", "INT")
            hist["first_seen"] = hist.get("first_seen", datetime.now().isoformat())
            if is_ok:
                hist["status"] = "alive"
            else:
                hist["status"] = "dead"
                dead += 1
            self.channel_history[stream_hash] = hist
            await asyncio.sleep(0.005)
        self.log(f"🧪 Проверено: {checked}, помечено dead: {dead}")

    def _pick_replacement_url_for_name(self, name: str, bad_url: str = "") -> Optional[str]:
        """Выбирает лучший URL для названия канала из найденных потоков."""
        key = self.clean_channel_name(name).lower()
        candidates = list(self.name_to_urls.get(key, set()))
        if bad_url in candidates:
            candidates.remove(bad_url)
        if not candidates:
            return None

        def score(u: str) -> int:
            s = 0
            lower = u.lower()
            if ".m3u8" in lower:
                s += 5
            if "https://" in lower:
                s += 2
            if "zabava-hlive.ngenix.net" in lower:
                s += 3
            return s

        candidates.sort(key=score, reverse=True)
        return candidates[0]

    async def refresh_repo_playlists(self):
        """Обновляет ВСЕ плейлисты в data/playlists: заменяет dead URL и добавляет новые каналы по категориям."""
        playlist_dir = DATA_DIR / "playlists"
        if not playlist_dir.exists():
            return

        self.log("🛠️ Тотальное обновление плейлистов репозитория...")
        for pl_file in playlist_dir.glob("*.m3u"):
            try:
                content = pl_file.read_text(encoding="utf-8")
            except Exception:
                continue

            lines = content.splitlines()
            out: List[str] = []
            existing_names: Set[str] = set()
            last_extinf = ""
            group_name = pl_file.stem.replace("_", " ")
            for i, line in enumerate(lines):
                if line.startswith("#EXTINF"):
                    last_extinf = line
                    m = re.search(r",\s*(.+)$", line)
                    if m:
                        existing_names.add(self.clean_channel_name(m.group(1)).lower())
                    out.append(line)
                    continue

                if line.startswith("http://") or line.startswith("https://"):
                    channel_name = "Unknown"
                    m = re.search(r",\s*(.+)$", last_extinf)
                    if m:
                        channel_name = m.group(1).strip()
                    repl = self._pick_replacement_url_for_name(channel_name, bad_url=line)
                    stream_hash = self.get_stream_hash(line)
                    status = self.channel_history.get(stream_hash, {}).get("status", "alive")
                    if status == "dead" and repl:
                        out.append(repl)
                        self.replaced_dead_count += 1
                    else:
                        out.append(line)
                    continue

                out.append(line)

            # Добавляем новые каналы в плейлист по соответствующей group-title / имени файла
            added_here = 0
            normalized_group = group_name.lower()
            for url, info in self.found_streams.items():
                name = self.clean_channel_name(info.get("name", "Unknown"))
                if name.lower() in existing_names:
                    continue
                grp = str(info.get("group", "")).lower()
                if normalized_group in grp or grp in normalized_group:
                    out.append(f'#EXTINF:-1 tvg-name="{name}" group-title="{info.get("group", group_name)}",{name}')
                    out.append(url)
                    existing_names.add(name.lower())
                    added_here += 1

            pl_file.write_text("\n".join(out) + "\n", encoding="utf-8")
            self.log(f"🧩 {pl_file.name}: замен dead={self.replaced_dead_count}, добавлено={added_here}")

    async def check_and_add(self, url: str, source: str = "scan", name: str = None, group: str = "IPTV") -> bool:
        """Проверяет и добавляет канал, НЕ удаляя старые"""
        async with self.semaphore:
            try:
                # Пропускаем исключенный домен
                if EXCLUDED_DOMAIN in url.lower():
                    return False
                lower_url = url.lower()
                if not any(token in lower_url for token in [".m3u8", ".m3u", ".ts", ".mpd", ".mp4", ".mkv", "manifest"]):
                    return False
                
                # Если канал уже есть - не дублируем, но ОБНОВЛЯЕМ метаданные времени
                if url in self.found_streams:
                    existing = self.found_streams[url]
                    existing["found_at"] = datetime.now().isoformat()
                    existing["source"] = source or existing.get("source", "scan")
                    if name:
                        existing["name"] = self.clean_channel_name(name)
                    if group:
                        existing["group"] = group
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
                
                # Добавляем канал (ограничение 150000)
                if len(self.found_streams) < 150000:
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
                    self.name_to_urls[channel_name.lower()].add(url)
                    
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

    def build_name_index(self):
        """Строит индекс каналов по имени."""
        self.name_to_urls = defaultdict(set)
        for url, info in self.found_streams.items():
            name = self.clean_channel_name(info.get('name', 'Unknown')).lower()
            self.name_to_urls[name].add(url)

    async def fetch_m3u_from_source(self, url: str) -> List[Dict]:
        """Загружает каналы из m3u плейлиста"""
        try:
            async with self.session.get(url, allow_redirects=True,
                                       timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_MEDIUM)) as response:
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

    def extract_candidate_playlist_links(self, html: str) -> Set[str]:
        """Извлекает ссылки на возможные плейлисты из HTML поисковой выдачи."""
        candidates: Set[str] = set()
        href_pattern = r'href=[\'"]([^\'"]+)[\'"]'
        for href in re.findall(href_pattern, html, re.IGNORECASE):
            clean = href.replace("&amp;", "&").strip()

            # Декодируем редиректы поисковиков вида /url?q=... или ?uddg=...
            if "url?q=" in clean:
                clean = clean.split("url?q=", 1)[1].split("&", 1)[0]
            elif "uddg=" in clean:
                clean = clean.split("uddg=", 1)[1].split("&", 1)[0]

            clean = urllib.parse.unquote(clean)
            if not clean.startswith(("http://", "https://")):
                continue
            if EXCLUDED_DOMAIN in clean.lower():
                continue

            lower = clean.lower()
            if any(mark in lower for mark in [".m3u", ".m3u8", "playlist", "iptv", "channels"]):
                candidates.add(clean)

        return candidates

    async def discover_channels_from_playlist_links(self, links: Set[str], source: str):
        """Пробует распарсить найденные ссылки как плейлисты и добавить каналы."""
        for link in list(links)[:100]:
            # Если это сразу поток, добавляем как канал
            if link.lower().endswith(".m3u8"):
                await self.check_and_add(link, source=source)
                continue

            # Если ссылка похожа на плейлист - пробуем распарсить
            if any(token in link.lower() for token in [".m3u", ".m3u8", ".txt", "playlist", "iptv"]):
                channels = await self.fetch_m3u_from_source(link)
                for channel in channels[:500]:
                    await self.check_and_add(
                        channel["url"],
                        source=source,
                        name=channel["name"],
                        group=channel["group"],
                    )
            await asyncio.sleep(0.05)

    async def scan_m3u_sources(self):
        """Сканирует публичные m3u плейлисты"""
        self.log("🌐 Сканирование публичных IPTV плейлистов...")
        sources = M3U_SOURCES[:self.m3u_source_limit]
        total_sources = len(sources)
        batch_size = 20
        processed_sources = 0
        added_channels = 0
        for start in range(0, total_sources, batch_size):
            batch = sources[start:start + batch_size]
            tasks = [self.fetch_m3u_from_source(source) for source in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            processed_sources += len(batch)
            self.log(f"⏱️ Прогресс источников: {processed_sources}/{total_sources}")
            for result in results:
                if isinstance(result, list):
                    for channel in result:
                        was_added = await self.check_and_add(
                            channel['url'],
                            source="m3u_source",
                            name=channel['name'],
                            group=channel['group'],
                        )
                        if was_added:
                            added_channels += 1
                            if added_channels % CHANNEL_PROGRESS_EVERY == 0:
                                self.log(f"📈 Прогресс добавления каналов: +{added_channels}")
            if processed_sources % SOURCE_PROGRESS_EVERY == 0 or processed_sources == total_sources:
                self.log(f"✅ Обработано источников: {processed_sources}/{total_sources}")

        self.log(f"🏁 Сканирование m3u-источников завершено: добавлено {added_channels} каналов")

    async def search_github_sources(self):
        """Ищет дополнительные m3u-источники через GitHub API."""
        self.log("🐙 Поиск новых источников через GitHub API...")
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "LiveM3U-Scanner/2026",
        }
        queries = [
            "iptv playlist extension:m3u",
            "live tv extension:m3u8",
            "russia iptv extension:m3u",
            "sports iptv extension:m3u",
        ]
        dynamic_sources: Set[str] = set()

        for idx, query in enumerate(queries, start=1):
            search_url = (
                f"https://api.github.com/search/code?"
                f"q={urllib.parse.quote(query)}&sort=indexed&order=desc&per_page=25"
            )
            try:
                async with self.session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_LONG)) as response:
                    if response.status != 200:
                        self.log(f"⚠️ GitHub API {response.status} для запроса '{query}'")
                        continue
                    payload = await response.json()
                    for item in payload.get("items", []):
                        html_url = item.get("html_url", "")
                        if "/blob/" in html_url:
                            raw_url = html_url.replace("https://github.com/", "https://raw.githubusercontent.com/").replace("/blob/", "/")
                            if raw_url.endswith((".m3u", ".m3u8", ".txt")):
                                dynamic_sources.add(raw_url)
                self.log(f"⏱️ GitHub поиск: {idx}/{len(queries)} запросов обработано")
            except Exception as e:
                self.log(f"⚠️ GitHub API ошибка '{query}': {e}")
            await asyncio.sleep(0.25)

        self.log(f"📦 Найдено {len(dynamic_sources)} новых GitHub-источников")
        for idx, source_url in enumerate(list(dynamic_sources)[:self.dynamic_source_limit], start=1):
            channels = await self.fetch_m3u_from_source(source_url)
            for channel in channels[:300]:
                await self.check_and_add(
                    channel["url"],
                    source="github_dynamic",
                    name=channel["name"],
                    group=channel["group"],
                )
            if idx % SOURCE_PROGRESS_EVERY == 0:
                self.log(f"⏱️ GitHub источники: {idx}/{min(len(dynamic_sources), self.dynamic_source_limit)}")
            await asyncio.sleep(0.1)

    async def search_web(self):
        """Поиск IPTV потоков через прямые сайты и поисковые системы"""
        self.log("🔍 Поиск по прямым сайтам и поисковым системам...")

        # 1. Сначала проверяем прямые URL сайтов (быстро и эффективно)
        self.log("📡 Проверка прямых источников...")
        direct_sites = DIRECT_SITES[:self.direct_sites_limit] if self.direct_sites_limit else DIRECT_SITES
        for idx, site_url in enumerate(direct_sites, start=1):
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': '*/*',
                }
                
                async with self.session.get(site_url, headers=headers,
                                          timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_MEDIUM),
                                          allow_redirects=True) as response:
                    if response.status == 200:
                        text = await response.text()
                        
                        # Извлекаем m3u8/m3u URL
                        m3u_pattern = r'https?[^\s"\'<>]+\.m3u8?[^\s"\'<>]*'
                        matches = re.findall(m3u_pattern, text, re.IGNORECASE)
                        
                        for match in matches[:50]:  # Максимум 50 URL из каждого источника
                            clean_url = match.replace('&amp;', '&').replace('"', '')
                            if clean_url.startswith('http') and EXCLUDED_DOMAIN not in clean_url:
                                await self.check_and_add(clean_url, source="direct_site")
                        
                        self.log(f"✅ Найдено {len(matches)} потоков в {site_url[:50]}")
                        
            except Exception as e:
                self.log(f"⚠️ Ошибка доступа к {site_url[:50]}: {e}")
            
            if idx % SOURCE_PROGRESS_EVERY == 0 or idx == len(direct_sites):
                self.log(f"⏱️ Прямые источники: {idx}/{len(direct_sites)}")
            await asyncio.sleep(0.5)  # Пауза между запросами

        # 2. Расширенный поиск через поисковые системы с прокси - Google, Yandex, Bing
        self.log("🔎 Поиск через поисковые системы (Google, Yandex, Bing)...")
        
        # Поисковые движки с разными параметрами
        search_engines = [
            ("Google", "https://www.google.com/search?q={query}&num=20&hl=ru"),
            ("Yandex", "https://yandex.ru/search/?text={query}&lr=213"),
            ("Bing", "https://www.bing.com/search?q={query}&count=20&setlang=ru"),
            ("DuckDuckGo", "https://duckduckgo.com/html/?q={query}&kl=ru-ru"),
        ]
        
        # Используем расширенный пул запросов: базовые + популярные каналы + GitHub dorks
        queries_to_use = list(SEARCH_QUERIES)
        for channel in POPULAR_CHANNEL_QUERIES:
            queries_to_use.extend([
                f"{channel} прямой эфир m3u8",
                f"{channel} live stream hls",
                f"{channel} iptv playlist m3u",
            ])
        queries_to_use.extend([
            "site:github.com iptv extension:m3u",
            "site:github.com inurl:raw m3u8 live tv",
            "site:raw.githubusercontent.com playlist.m3u",
            "site:gitlab.com iptv m3u8",
        ])
        # Дедупликация с сохранением порядка
        queries_to_use = list(dict.fromkeys(queries_to_use))
        if self.search_query_limit:
            queries_to_use = queries_to_use[:self.search_query_limit]
        
        for engine_name, engine_url_template in search_engines:
            self.log(f"📡 Поиск через {engine_name}...")
            for i, query in enumerate(queries_to_use):
                try:
                    encoded_query = urllib.parse.quote(query)
                    search_url = engine_url_template.format(query=encoded_query)
                    
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                        'Accept-Encoding': 'gzip, deflate',
                        'Connection': 'keep-alive',
                    }
                    
                    async with self.session.get(search_url, headers=headers,
                                              timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_MEDIUM),
                                              allow_redirects=True) as response:
                        if response.status == 200:
                            text = await response.text()

                            # Извлекаем m3u8/m3u URL из результатов поиска
                            m3u_pattern = r'https?://[^\s"\'<>]+\.m3u8?[^\s"\'<>]*'
                            matches = re.findall(m3u_pattern, text, re.IGNORECASE)
                            
                            # Также ищем ссылки на плейлисты в формате http://.../playlist.m3u
                            playlist_pattern = r'https?://[^\s"\'<>]*(?:playlist|iptv|stream)[^\s"\'<>]*\.m3u8?[^\s"\'<>]*'
                            playlist_matches = re.findall(playlist_pattern, text, re.IGNORECASE)
                            
                            all_matches = list(set(matches + playlist_matches))
                            candidate_links = self.extract_candidate_playlist_links(text)

                            for match in all_matches[:30]:  # Максимум 30 URL из каждого запроса
                                clean_url = match.replace('&amp;', '&').replace('"', '').replace("'", "")
                                if clean_url.startswith('http') and EXCLUDED_DOMAIN not in clean_url:
                                    await self.check_and_add(clean_url, source="web_search")

                            # Дополнительно: пробуем вытянуть ссылки на m3u-плейлисты из HTML результатов
                            if candidate_links:
                                await self.discover_channels_from_playlist_links(
                                    candidate_links,
                                    source="web_search_discovery",
                                )
                                    
                            if all_matches:
                                self.log(f"✅ {engine_name}: найдено {len(all_matches)} ссылок по запросу '{query[:40]}...'")

                except Exception as e:
                    self.log(f"⚠️ {engine_name} ошибка поиска по '{query[:30]}...': {e}")

                if (i + 1) % SOURCE_PROGRESS_EVERY == 0 or (i + 1) == len(queries_to_use):
                    self.log(f"⏱️ {engine_name}: запросы {i + 1}/{len(queries_to_use)}")
                await asyncio.sleep(0.5)  # Пауза между запросами чтобы не блокировали
            
            self.log(f"✓ Завершен поиск через {engine_name}")
            await asyncio.sleep(2)  # Пауза между поисковыми системами
        
        # 3. Дополнительный поиск по специализированным IPTV форумам и сайтам
        self.log("🌐 Поиск на IPTV форумах и специализированных сайтах...")
        iptv_sites = [
            "https://4pda.to/forum/index.php?showtopic=346083&view=findpost",
            "https://rutracker.org/forum/tracker.php?nm=iptv",
            "https://www.hdclub.org/browse.php?search=iptv&incldead=0&blah=0",
            "https://torrents-ru.org/forum/tracker.php?nm=iptv+m3u",
            "https://iptv.ru/channels",
            "https://peers.tv/channels/",
            "https://tv.yandex.ru/",
        ]
        if self.iptv_sites_limit:
            iptv_sites = iptv_sites[:self.iptv_sites_limit]
        
        for site in iptv_sites:
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'text/html,application/xhtml+xml',
                }
                async with self.session.get(site, headers=headers,
                                          timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_MEDIUM),
                                          allow_redirects=True) as response:
                    if response.status == 200:
                        text = await response.text()
                        m3u_pattern = r'https?://[^\s"\'<>]+\.m3u8?[^\s"\'<>]*'
                        matches = re.findall(m3u_pattern, text, re.IGNORECASE)
                        
                        for match in matches[:20]:
                            clean_url = match.replace('&amp;', '&').replace('"', '')
                            if clean_url.startswith('http') and EXCLUDED_DOMAIN not in clean_url:
                                await self.check_and_add(clean_url, source="forum_search")
                                
            except Exception as e:
                self.log(f"⚠️ Ошибка доступа к форуму {site[:50]}: {e}")
            
            await asyncio.sleep(1)

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

        # Приоритетные каналы идут первыми - с проверкой на прокси (GitHub CDN без прокси)
        for url, info in priority_streams:
            name = info.get('name', 'Channel')
            group = info.get('group', 'IPTV')
            
            # Проверяем нужен ли прокси для приоритетных каналов
            use_proxy = not any(domain in url for domain in DIRECT_DOMAINS) and \
                       not any(domain in url for domain in NO_PROXY_DOMAINS)
            
            if use_proxy:
                parsed = urllib.parse.urlparse(url)
                stream_url = f"{PROXY_BASE}{parsed.netloc}{parsed.path}"
                if parsed.query:
                    stream_url += '?' + parsed.query
            else:
                stream_url = url
            
            m3u_content += f'#EXTINF:-1 tvg-name="{name}" group-title="{group}",{name} ⭐\n'
            m3u_content += f'{stream_url}\n\n'

        # Затем российские каналы - ВСЕ С ПРОКСИ кроме zabava-hlive.ngenix.net и GitHub CDN
        for url, info in ru_streams:
            name = info.get('name', 'Channel')
            group = info.get('group', 'IPTV')
            
            # Определяем нужен ли прокси - только zabava-hlive.ngenix.net и GitHub CDN без прокси
            use_proxy = not any(domain in url for domain in DIRECT_DOMAINS) and \
                       not any(domain in url for domain in NO_PROXY_DOMAINS)
            
            if use_proxy:
                parsed = urllib.parse.urlparse(url)
                stream_url = f"{PROXY_BASE}{parsed.netloc}{parsed.path}"
                if parsed.query:
                    stream_url += '?' + parsed.query
            else:
                stream_url = url
            
            m3u_content += f'#EXTINF:-1 tvg-name="{name}" group-title="{group}",{name}\n'
            m3u_content += f'{stream_url}\n\n'

        # Затем международные каналы - ВСЕ С ПРОКСИ кроме zabava-hlive.ngenix.net и GitHub CDN
        for url, info in int_streams:
            name = info.get('name', 'Channel')
            group = info.get('group', 'IPTV')
            
            # Определяем нужен ли прокси - только zabava-hlive.ngenix.net и GitHub CDN без прокси
            use_proxy = not any(domain in url for domain in DIRECT_DOMAINS) and \
                       not any(domain in url for domain in NO_PROXY_DOMAINS)
            
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
                    self.name_to_urls[info.get('name', 'Unknown').lower()].add(url)
                
                self.log(f"📂 Загружено {len(self.found_streams)} ранее найденных потоков")
            except Exception as e:
                self.log(f"⚠️ Не удалось загрузить потоки: {e}")

    async def save_streams(self):
        """Сохраняет найденные потоки"""
        with open(FOUND_STREAMS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.found_streams, f, ensure_ascii=False, indent=2)
        self.log(f"💾 Сохранено {len(self.found_streams)} потоков")

    async def split_into_thematic_playlists(self):
        """Разделяет плейлист на тематические категории с прокси (кроме zabava-hlive.ngenix.net)"""
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
                
                # Генерируем контент с прокси для каждого канала
                group_content = header
                group_content += f"# Категория: {group_name}\n"
                group_content += f"# Каналов: {len(channels)}\n"
                group_content += f"# Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                group_content += "# ВСЕ каналы с прокси кроме zabava-hlive.ngenix.net\n\n"
                
                for channel in channels:
                    # Извлекаем URL из канала - ищем строку начинающуюся с http после #EXTINF
                    lines = channel.strip().split('\n')
                    url = None
                    for line in lines:
                        line = line.strip()
                        if line.startswith('http'):
                            url = line
                            break
                    
                    if url:
                        name_match = re.search(r'tvg-name="([^"]*)"', channel)
                        group_match = re.search(r'group-title="([^"]*)"', channel)
                        
                        name = name_match.group(1) if name_match else "Channel"
                        grp = group_match.group(1) if group_match else "IPTV"
                        
                        # Применяем прокси кроме для zabava-hlive.ngenix.net и GitHub CDN
                        use_proxy = not any(domain in url for domain in DIRECT_DOMAINS) and \
                                   not any(domain in url for domain in NO_PROXY_DOMAINS)
                        
                        if use_proxy:
                            parsed = urllib.parse.urlparse(url)
                            stream_url = f"{PROXY_BASE}{parsed.netloc}{parsed.path}"
                            if parsed.query:
                                stream_url += '?' + parsed.query
                        else:
                            stream_url = url
                        
                        group_content += f'#EXTINF:-1 tvg-name="{name}" group-title="{grp}",{name}\n'
                        group_content += f'{stream_url}\n\n'
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(group_content)

            self.log(f"✅ Создано {len(groups)} тематических плейлистов с прокси")

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

    async def restore_channels_from_history(self):
        """Возвращает каналы из истории в общий пул, чтобы они снова попали в обычный и тематические плейлисты."""
        restored = 0
        for _, hist in self.channel_history.items():
            url = str(hist.get("url", "")).strip()
            if not url or url in self.found_streams:
                continue
            lower_url = url.lower()
            if EXCLUDED_DOMAIN in lower_url:
                continue
            if not any(token in lower_url for token in [".m3u8", ".m3u", ".ts", ".mpd", ".mp4", ".mkv", "manifest"]):
                continue

            channel_name = self.clean_channel_name(hist.get("name", "Unknown"))
            is_ru = any(kw in lower_url for kw in RU_KEYWORDS) or any(kw in channel_name.lower() for kw in RU_KEYWORDS)
            group = hist.get("group") or ("RU" if is_ru else "IPTV")
            stream_hash = hist.get("hash") or self.get_stream_hash(url)

            self.found_streams[url] = {
                "name": channel_name,
                "url": url,
                "found_at": datetime.now().isoformat(),
                "country": hist.get("country", "RU" if is_ru else "INT"),
                "group": group,
                "source": "history_restore",
                "hash": stream_hash,
            }
            self.name_to_urls[channel_name.lower()].add(url)
            restored += 1

        if restored:
            self.log(f"♻️ Восстановлено из истории: {restored} каналов")
        else:
            self.log("♻️ Восстановление из истории: нечего возвращать")

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
        self.build_name_index()
        if self.fast_scan:
            self.log(f"⚡ FAST_SCAN=1: ускоренная проверка существующих потоков (limit={self.validate_sample_limit})")
        await self.validate_existing_streams(sample_limit=self.validate_sample_limit)
        
        old_count = len(self.found_streams)
        self.new_channels_count = 0

        # 0. Сначала добавляем приоритетные каналы (Дождь и другие важные)
        await self.add_priority_channels()

        # 1. Сканирование m3u источников
        await self.scan_m3u_sources()
        await self.search_github_sources()

        # 2. Поиск по сайтам
        if self.fast_scan:
            self.log("⚡ FAST_SCAN=1: web-поиск включен с уменьшенным объемом запросов")
        await self.search_web()
        await self.restore_channels_from_history()

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
        # Обновляем все существующие плейлисты репозитория: замена dead + добавление новых каналов
        await self.refresh_repo_playlists()

        self.log(f"♻️ Всего заменено нерабочих ссылок: {self.replaced_dead_count}")

        await self.close_session()


async def main():
    """Точка входа - сканирование с автообновлением каждые 30 минут"""
    DATA_DIR.mkdir(exist_ok=True)
    
    scanner = IPTVScanner()
    await scanner.run_scan()
    
    print("\n" + "="*60)
    print("✅ Сканирование завершено успешно!")
    print("="*60)


async def continuous_scan():
    """Непрерывное сканирование с обновлением каждые 30 минут"""
    DATA_DIR.mkdir(exist_ok=True)
    
    scan_count = 0
    while True:
        scan_count += 1
        print(f"\n{'='*60}")
        print(f"🔄 Запуск сканирования #{scan_count}")
        print(f"{'='*60}\n")
        
        scanner = IPTVScanner()
        await scanner.run_scan()
        
        print(f"\n{'='*60}")
        print(f"✅ Сканирование #{scan_count} завершено!")
        print(f"⏳ Следующее сканирование через 30 минут...")
        print(f"{'='*60}\n")
        
        # Ждем 30 минут (1800 секунд) перед следующим сканированием
        await asyncio.sleep(1800)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--continuous":
        # Режим непрерывного сканирования каждые 30 минут
        print("🚀 Запуск в режиме непрерывного сканирования (каждые 30 минут)...")
        asyncio.run(continuous_scan())
    else:
        # Одиночное сканирование (для GitHub Actions)
        asyncio.run(main())
