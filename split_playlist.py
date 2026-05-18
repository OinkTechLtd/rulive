#!/usr/bin/env python3
import re

def split_playlist_by_groups(input_file, output_dir):
    """Разделяет большой M3U плейлист на тематические по group-title"""
    
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Разбиваем на записи (каждая запись начинается с #EXTINF)
    entries = re.split(r'(?=#EXTINF)', content)
    
    # Группируем каналы по group-title
    groups = {}
    header = "#EXTM3U\n"
    
    for entry in entries:
        if not entry.strip():
            continue
        
        if entry.startswith('#EXTM3U'):
            header = entry
            continue
        
        # Извлекаем group-title
        match = re.search(r'group-title="([^"]*)"', entry)
        if match:
            group_name = match.group(1)
            if group_name not in groups:
                groups[group_name] = []
            groups[group_name].append(entry)
        else:
            # Каналы без группы - в отдельную категорию
            if 'No Group' not in groups:
                groups['No Group'] = []
            groups['No Group'].append(entry)
    
    # Создаем главный индексный файл
    index_content = "#EXTM3U\n"
    index_content += "# Плейлисты разбиты по категориям для лучшей производительности\n"
    index_content += "# Выберите нужный плейлист или загрузите несколько\n\n"
    
    # Сортируем группы: сначала Россия, потом страны, потом остальное
    def sort_key(group):
        if group == 'IPTV' or group == 'Основные':
            return (0, group)
        if group in ['Russia', 'Москва', 'Санкт-Петербург']:
            return (1, group)
        if any(cyrillic in group for cyrillic in 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ'):
            return (2, group)
        return (3, group)
    
    sorted_groups = sorted(groups.keys(), key=sort_key)
    
    for group_name in sorted_groups:
        channels = groups[group_name]
        if not channels:
            continue
        
        # Создаем имя файла
        safe_name = re.sub(r'[^\w\s\-\u0400-\u04FF]', '_', group_name).strip()
        safe_name = re.sub(r'\s+', '_', safe_name)
        filename = f"{safe_name}.m3u"
        
        # Записываем файл группы
        filepath = f"{output_dir}/{filename}"
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(header)
            f.write(f"# Категория: {group_name}\n")
            f.write(f"# Каналов: {len(channels)}\n\n")
            for channel in channels:
                f.write(channel)
        
        # Добавляем в индекс
        index_content += f"#EXTINF:-1 group-title=\"Categories\",{group_name} ({len(channels)} каналов)\n"
        index_content += f"{filename}\n\n"
        
        print(f"Создан плейлист: {filename} ({len(channels)} каналов)")
    
    # Записываем индексный файл
    with open(f"{output_dir}/INDEX.m3u", 'w', encoding='utf-8') as f:
        f.write(index_content)
    
    print(f"\nВсего создано плейлистов: {len(groups)}")
    print(f"Индексный файл: {output_dir}/INDEX.m3u")

if __name__ == '__main__':
    split_playlist_by_groups('/workspace/data/playlist.m3u', '/workspace/data/playlists')
