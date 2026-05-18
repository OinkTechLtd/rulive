/* === SmartTVLove Player JS === */

// ─── STATE ───────────────────────────────────────────────────────────────────
let allChannels = [];
let filteredChannels = [];
let currentChannel = null;
let hlsInstance = null;
let dashPlayer = null;
let sidebarOpen = true;
let controlsTimer = null;
let startupWatchdog = null;

const HLS_CDNS = [
  'https://cdn.jsdelivr.net/npm/hls.js@latest',
  'https://unpkg.com/hls.js@latest/dist/hls.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/hls.js/1.5.17/hls.min.js'
];
const DASH_CDNS = [
  'https://cdn.dashjs.org/latest/dash.all.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/dashjs/4.7.4/dash.all.min.js'
];

const video = document.getElementById('videoPlayer');
const channelList = document.getElementById('channelList');
const groupSelect = document.getElementById('groupSelect');
const searchInput = document.getElementById('searchInput');
const playBtn = document.getElementById('playBtn');
const muteBtn = document.getElementById('muteBtn');
const progressBar = document.getElementById('progressBar');
const currentTimeEl = document.getElementById('currentTime');
const durationEl = document.getElementById('duration');
const qualitySelect = document.getElementById('qualitySelect');
const buffering = document.getElementById('buffering');
const noChannel = document.getElementById('noChannel');
const infoBar = document.getElementById('infoBar');
const nowPlaying = document.getElementById('nowPlaying');
const controlsOverlay = document.getElementById('controlsOverlay');
const toast = document.getElementById('toast');

// ─── INIT ─────────────────────────────────────────────────────────────────────
window.addEventListener('load', async () => {
  setVolume(80);
  setupVideoEvents();
  setupControlsHide();
  await ensurePlaybackEngines();
  const saved = localStorage.getItem('stv_last_url');
  if (saved) document.getElementById('m3uUrl').value = saved;
});



function loadScriptWithFallback(urls, checker) {
  if (checker()) return Promise.resolve(true);
  const [first, ...rest] = urls;
  if (!first) return Promise.resolve(false);

  return new Promise(resolve => {
    const script = document.createElement('script');
    script.src = first;
    script.async = true;
    script.crossOrigin = 'anonymous';
    script.onload = () => resolve(checker());
    script.onerror = () => resolve(false);
    document.head.appendChild(script);
  }).then(ok => ok ? true : loadScriptWithFallback(rest, checker));
}

async function ensurePlaybackEngines() {
  await Promise.all([
    loadScriptWithFallback(HLS_CDNS, () => typeof window.Hls !== 'undefined'),
    loadScriptWithFallback(DASH_CDNS, () => typeof window.dashjs !== 'undefined')
  ]);
}

function startStartupWatchdog() {
  clearTimeout(startupWatchdog);
  startupWatchdog = setTimeout(() => {
    if (video.readyState < 2 && currentChannel) {
      showToast('⚠️ Поток долго запускается. Переподключаем...');
      const idx = allChannels.indexOf(currentChannel);
      if (idx !== -1) playChannel(idx);
    }
  }, 10000);
}

// ─── M3U LOADING ──────────────────────────────────────────────────────────────
async function loadPlaylist() {
  const url = document.getElementById('m3uUrl').value.trim();
  if (!url) { showToast('⚠️ Введите ссылку на M3U плейлист'); return; }

  showToast('⏳ Загрузка плейлиста...');
  document.getElementById('loadBtn').textContent = '⏳';

  try {
    // Try CORS proxy if direct fails
    let text = '';
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error('Direct fetch failed');
      text = await resp.text();
    } catch {
      // Try CORS proxies
      const proxies = [
        `https://api.allorigins.win/raw?url=${encodeURIComponent(url)}`,
        `https://corsproxy.io/?${encodeURIComponent(url)}`,
        `https://cors-anywhere.herokuapp.com/${url}`,
        `https://secure-272717.vercel.app/${url}`,
        `https://secure-272717.tatnet.app/${url}`,
        `https://secure-272717.vercel.app/${url}`,
        `https://proxyvideo.vercel.app/${url}`,
        `https://secure-ridge-22999-537c838d4a8a.herokuapp.com/`
      ];
      let success = false;
      for (const proxy of proxies) {
        try {
          const resp = await fetch(proxy);
          if (resp.ok) { text = await resp.text(); success = true; break; }
        } catch {}
      }
      if (!success) throw new Error('Не удалось загрузить плейлист. Попробуйте другую ссылку или Raw-ссылку с GitHub.');
    }

    parseM3U(text);
    localStorage.setItem('stv_last_url', url);
    showToast(`✅ Загружено ${allChannels.length} каналов`);
  } catch (e) {
    showToast('❌ ' + e.message);
  } finally {
    document.getElementById('loadBtn').textContent = '▶ Загрузить';
  }
}

function loadZabawa() {
  const zabawa = 'https://raw.githubusercontent.com/CrocoUser/zabava-project/refs/heads/main/zabava-full.m3u';
  document.getElementById('m3uUrl').value = zabawa;
  loadPlaylist();
}

// ─── M3U PARSER ───────────────────────────────────────────────────────────────
function parseM3U(text) {
  allChannels = [];
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
  let current = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith('#EXTM3U')) continue;

    if (line.startsWith('#EXTINF:')) {
      current = parseExtInf(line);
    } else if (line.startsWith('#EXTVLCOPT') || line.startsWith('#EXTGRP')) {
      // skip VLC opts, handle group
      if (line.startsWith('#EXTGRP:') && current) {
        current.group = line.replace('#EXTGRP:', '').trim();
      }
    } else if (!line.startsWith('#') && line.length > 0) {
      if (current) {
        current.url = line;
        allChannels.push(current);
        current = null;
      }
    }
  }

  buildGroupList();
  renderChannels(allChannels);
  updateCount(allChannels.length);
  document.getElementById('embedBtn').disabled = false;
}

function parseExtInf(line) {
  const ch = { name: 'Канал', group: 'Без группы', logo: '', url: '' };

  // Extract duration and name (after last comma)
  const mainMatch = line.match(/#EXTINF:(-?\d+)\s*(.*),(.*)$/s);
  if (mainMatch) {
    const attrs = mainMatch[2];
    ch.name = mainMatch[3].trim() || 'Канал';

    const logoMatch = attrs.match(/tvg-logo="([^"]+)"/i);
    if (logoMatch) ch.logo = logoMatch[1];

    const groupMatch = attrs.match(/group-title="([^"]+)"/i);
    if (groupMatch) ch.group = groupMatch[1];

    const nameMatch = attrs.match(/tvg-name="([^"]+)"/i);
    if (nameMatch && !ch.name) ch.name = nameMatch[1];
  } else {
    // Fallback
    const commaIdx = line.lastIndexOf(',');
    if (commaIdx !== -1) ch.name = line.slice(commaIdx + 1).trim();
  }

  return ch;
}

// ─── GROUPS ───────────────────────────────────────────────────────────────────
function buildGroupList() {
  const groups = ['', ...new Set(allChannels.map(c => c.group).filter(Boolean)).values()];
  groupSelect.innerHTML = '';
  groups.forEach(g => {
    const opt = document.createElement('option');
    opt.value = g;
    opt.textContent = g ? `📂 ${g}` : `📺 Все каналы (${allChannels.length})`;
    groupSelect.appendChild(opt);
  });
  groupSelect.disabled = false;
}

function filterByGroup() {
  const group = groupSelect.value;
  const search = searchInput.value.toLowerCase();
  applyFilters(group, search);
}

function filterChannels() {
  const group = groupSelect.value;
  const search = searchInput.value.toLowerCase();
  applyFilters(group, search);
}

function applyFilters(group, search) {
  filteredChannels = allChannels.filter(ch => {
    const matchGroup = !group || ch.group === group;
    const matchSearch = !search || ch.name.toLowerCase().includes(search) || ch.group.toLowerCase().includes(search);
    return matchGroup && matchSearch;
  });
  renderChannels(filteredChannels);
  updateCount(filteredChannels.length);
}

// ─── RENDER CHANNELS ──────────────────────────────────────────────────────────
function renderChannels(channels) {
  if (channels.length === 0) {
    channelList.innerHTML = `<div class="empty-state"><div class="empty-icon">🔍</div><p>Каналы не найдены</p></div>`;
    return;
  }

  channelList.innerHTML = '';
  channels.forEach((ch, idx) => {
    const div = document.createElement('div');
    div.className = 'channel-item' + (currentChannel === ch ? ' active' : '');
    div.dataset.idx = allChannels.indexOf(ch);

    const thumb = ch.logo
      ? `<div class="ch-thumb"><img src="${ch.logo}" alt="" onerror="this.parentElement.innerHTML='📺'" /></div>`
      : `<div class="ch-thumb">📺</div>`;

    div.innerHTML = `
      ${thumb}
      <div class="ch-info-item">
        <div class="ch-name">${escapeHtml(ch.name)}</div>
        <div class="ch-group-tag">${escapeHtml(ch.group || '')}</div>
      </div>
      <span class="ch-play-icon">▶</span>
    `;
    div.addEventListener('click', () => playChannel(allChannels.indexOf(ch)));
    channelList.appendChild(div);
  });
}

function updateCount(n) {
  document.getElementById('channelCount').textContent = `${n} каналов`;
}

// ─── PLAY ─────────────────────────────────────────────────────────────────────
function playChannel(idx) {
  const ch = allChannels[idx];
  if (!ch) return;
  currentChannel = ch;

  // Update UI
  document.querySelectorAll('.channel-item').forEach(el => el.classList.remove('active'));
  document.querySelector(`[data-idx="${idx}"]`)?.classList.add('active');

  document.getElementById('currentChannelName').textContent = ch.name;
  nowPlaying.textContent = ch.name;
  document.getElementById('infoTitle').textContent = ch.name;
  document.getElementById('infoGroup').textContent = ch.group || '';
  document.getElementById('embedBtn').disabled = false;

  const logo = document.getElementById('channelLogo');
  logo.src = ch.logo || '';
  logo.style.display = ch.logo ? 'block' : 'none';

  document.getElementById('directLink').href = ch.url;
  infoBar.style.display = 'flex';
  noChannel.style.display = 'none';
  document.getElementById('topbar-title') && (document.getElementById('topbar-title').textContent = ch.name);

  // Reset quality
  qualitySelect.innerHTML = '<option value="auto">Auto</option>';

  // Stop previous
  destroyPlayer();
  showBuffering(true);
  startStartupWatchdog();

  const url = ch.url;
  const ext = url.split('?')[0].split('.').pop().toLowerCase();

  if (url.includes('.m3u8') || url.includes('hls') || ext === 'm3u8' || ext === 'm3u') {
    playHLS(url);
  } else if (url.includes('.mpd') || url.includes('dash') || ext === 'mpd') {
    playDASH(url);
  } else {
    playNative(url);
  }

  // On mobile close sidebar
  if (window.innerWidth <= 768) closeSidebar();
}

function playHLS(url) {
  if (window.Hls && Hls.isSupported()) {
    hlsInstance = new Hls({
      enableWorker: true,
      lowLatencyMode: true,
      backBufferLength: 90,
    });
    hlsInstance.loadSource(url);
    hlsInstance.attachMedia(video);

    hlsInstance.on(Hls.Events.MANIFEST_PARSED, (_, data) => {
      buildHLSQualities(data.levels);
      video.play().catch(() => {});
    });

    hlsInstance.on(Hls.Events.LEVEL_SWITCHED, (_, data) => {
      const lvl = hlsInstance.levels[data.level];
      if (lvl) qualitySelect.value = data.level;
    });

    hlsInstance.on(Hls.Events.ERROR, (_, data) => {
      if (data.fatal) {
        showToast('⚠️ Ошибка HLS потока. Пробуем восстановить...');
        hlsInstance.recoverMediaError();
      }
    });
  } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
    // Native HLS (Safari/iOS)
    playNative(url);
  } else {
    playNative(url);
  }
}

function playDASH(url) {
  if (window.dashjs) {
    dashPlayer = dashjs.MediaPlayer().create();
    dashPlayer.initialize(video, url, true);
    dashPlayer.on(dashjs.MediaPlayer.events.STREAM_INITIALIZED, () => {
      buildDASHQualities();
    });
  } else {
    playNative(url);
  }
}

function playNative(url) {
  video.src = url;
  video.load();
  video.play().catch(e => {
    showToast('⚠️ Не удалось воспроизвести. Проверьте URL.');
    console.error(e);
  });
}

function destroyPlayer() {
  if (hlsInstance) { hlsInstance.destroy(); hlsInstance = null; }
  if (dashPlayer) { dashPlayer.reset(); dashPlayer = null; }
  video.src = '';
}

// ─── HLS QUALITY ─────────────────────────────────────────────────────────────
function buildHLSQualities(levels) {
  qualitySelect.innerHTML = '<option value="-1">Auto</option>';
  levels.forEach((lvl, i) => {
    const opt = document.createElement('option');
    opt.value = i;
    const label = lvl.height ? `${lvl.height}p` : (lvl.bitrate ? `${Math.round(lvl.bitrate/1000)}kbps` : `Уровень ${i+1}`);
    opt.textContent = label;
    qualitySelect.appendChild(opt);
  });
}

function buildDASHQualities() {
  if (!dashPlayer) return;
  const bitrateList = dashPlayer.getBitrateInfoListFor('video');
  if (!bitrateList || !bitrateList.length) return;
  qualitySelect.innerHTML = '<option value="-1">Auto</option>';
  bitrateList.forEach((b, i) => {
    const opt = document.createElement('option');
    opt.value = i;
    opt.textContent = b.height ? `${b.height}p` : `${Math.round(b.bitrate/1000)}kbps`;
    qualitySelect.appendChild(opt);
  });
}

function changeQuality() {
  const val = parseInt(qualitySelect.value);
  if (hlsInstance) {
    hlsInstance.currentLevel = val; // -1 = auto
    showToast(val === -1 ? '🔄 Качество: Auto' : `📺 Качество: ${qualitySelect.options[qualitySelect.selectedIndex].text}`);
  } else if (dashPlayer) {
    if (val === -1) {
      dashPlayer.setAutoSwitchQualityFor('video', true);
    } else {
      dashPlayer.setAutoSwitchQualityFor('video', false);
      dashPlayer.setQualityFor('video', val);
    }
    showToast(`📺 Качество: ${qualitySelect.options[qualitySelect.selectedIndex].text}`);
  }
}

// ─── VIDEO EVENTS ─────────────────────────────────────────────────────────────
function setupVideoEvents() {
  video.addEventListener('playing', () => { showBuffering(false); clearTimeout(startupWatchdog); playBtn.textContent = '⏸'; });
  video.addEventListener('pause', () => { playBtn.textContent = '▶'; });
  video.addEventListener('waiting', () => showBuffering(true));
  video.addEventListener('canplay', () => showBuffering(false));
  video.addEventListener('ended', () => { playBtn.textContent = '▶'; });
  video.addEventListener('timeupdate', updateProgress);
  video.addEventListener('durationchange', updateDuration);
  video.addEventListener('volumechange', () => {
    muteBtn.textContent = video.muted || video.volume === 0 ? '🔇' : '🔊';
  });
  video.addEventListener('error', () => {
    showBuffering(false);
    if (currentChannel) showToast('❌ Ошибка воспроизведения потока');
  });

  // Click to play/pause
  video.addEventListener('click', togglePlay);
}

function showBuffering(v) {
  buffering.style.display = v ? 'flex' : 'none';
}

function updateProgress() {
  if (!video.duration || isNaN(video.duration)) return;
  const pct = (video.currentTime / video.duration) * 100;
  progressBar.value = pct;
  currentTimeEl.textContent = formatTime(video.currentTime);
}

function updateDuration() {
  durationEl.textContent = isFinite(video.duration) ? formatTime(video.duration) : 'Live 🔴';
}

function formatTime(s) {
  if (!isFinite(s)) return '0:00';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
}

function pad(n) { return n.toString().padStart(2, '0'); }

// ─── CONTROLS ─────────────────────────────────────────────────────────────────
function togglePlay() {
  if (!currentChannel) return;
  video.paused ? video.play() : video.pause();
}

function seekTo(pct) {
  if (video.duration && isFinite(video.duration)) {
    video.currentTime = (pct / 100) * video.duration;
  }
}

function seekBack() { video.currentTime = Math.max(0, video.currentTime - 10); }
function seekFwd() { video.currentTime = Math.min(video.duration || Infinity, video.currentTime + 10); }

function setVolume(val) {
  video.volume = val / 100;
  document.getElementById('volumeBar').value = val;
}

function toggleMute() {
  video.muted = !video.muted;
  muteBtn.textContent = video.muted ? '🔇' : '🔊';
}

function toggleFullscreen() {
  const wrapper = document.getElementById('videoWrapper');
  if (!document.fullscreenElement) {
    wrapper.requestFullscreen?.() || wrapper.webkitRequestFullscreen?.() || wrapper.mozRequestFullScreen?.();
  } else {
    document.exitFullscreen?.() || document.webkitExitFullscreen?.() || document.mozCancelFullScreen?.();
  }
}

function togglePIP() {
  if (document.pictureInPictureElement) {
    document.exitPictureInPicture();
  } else if (video.requestPictureInPicture) {
    video.requestPictureInPicture().catch(() => showToast('PiP не поддерживается'));
  }
}

function setupControlsHide() {
  const wrapper = document.getElementById('videoWrapper');
  wrapper.addEventListener('mousemove', () => {
    controlsOverlay.classList.add('always-show');
    clearTimeout(controlsTimer);
    controlsTimer = setTimeout(() => controlsOverlay.classList.remove('always-show'), 3000);
  });
}

// ─── SIDEBAR ──────────────────────────────────────────────────────────────────
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  if (window.innerWidth <= 768) {
    sidebar.classList.toggle('open');
  } else {
    const layout = document.getElementById('appLayout');
    sidebarOpen = !sidebarOpen;
    sidebar.style.display = sidebarOpen ? 'flex' : 'none';
  }
}

function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
}

// ─── EMBED ────────────────────────────────────────────────────────────────────
function openEmbedModal() {
  if (!currentChannel) { showToast('⚠️ Сначала выберите канал'); return; }

  const ch = currentChannel;
  const embedUrl = `embed.html?url=${encodeURIComponent(ch.url)}&name=${encodeURIComponent(ch.name)}&logo=${encodeURIComponent(ch.logo || '')}`;
  const fullEmbedUrl = window.location.origin + window.location.pathname.replace('player.html', '') + embedUrl;

  const embedCode = `<iframe src="${fullEmbedUrl}" width="640" height="360" frameborder="0" allowfullscreen allow="autoplay; encrypted-media; fullscreen; picture-in-picture" title="${escapeHtml(ch.name)}"></iframe>`;

  document.getElementById('embedChannelName').textContent = ch.name;
  document.getElementById('embedCode').value = embedCode;

  // Preview
  document.getElementById('embedPreview').innerHTML = `<iframe src="${embedUrl}" width="100%" height="200" frameborder="0" allowfullscreen allow="autoplay; encrypted-media; fullscreen"></iframe>`;

  document.getElementById('embedModal').style.display = 'flex';
  // Store for open button
  document.getElementById('embedModal').dataset.embedUrl = embedUrl;
}

function closeEmbedModal(e) {
  if (!e || e.target === document.getElementById('embedModal')) {
    document.getElementById('embedModal').style.display = 'none';
    document.getElementById('embedPreview').innerHTML = '';
  }
}

function copyEmbed() {
  const code = document.getElementById('embedCode').value;
  navigator.clipboard.writeText(code).then(() => {
    document.getElementById('copyEmbedBtn').textContent = '✓ Скопировано!';
    setTimeout(() => document.getElementById('copyEmbedBtn').textContent = '📋 Копировать код', 2000);
    showToast('✅ Embed код скопирован');
  });
}

function openEmbedPlayer() {
  const url = document.getElementById('embedModal').dataset.embedUrl;
  if (url) window.open(url, '_blank');
}

// ─── TOAST ────────────────────────────────────────────────────────────────────
let toastTimer;
function showToast(msg) {
  toast.textContent = msg;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 3000);
}

// ─── UTILS ────────────────────────────────────────────────────────────────────
function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Keyboard shortcuts
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  switch(e.code) {
    case 'Space': e.preventDefault(); togglePlay(); break;
    case 'ArrowLeft': seekBack(); break;
    case 'ArrowRight': seekFwd(); break;
    case 'ArrowUp': setVolume(Math.min(100, Math.round(video.volume*100)+5)); break;
    case 'ArrowDown': setVolume(Math.max(0, Math.round(video.volume*100)-5)); break;
    case 'KeyM': toggleMute(); break;
    case 'KeyF': toggleFullscreen(); break;
  }
});
