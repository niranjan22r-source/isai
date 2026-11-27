# ISAI

**Your music. Your space.**

ISAI is a modern, lightweight, Linux-native music player built with Python and
PySide6. It aims to feel at home on the Linux desktop: fast, quiet, and free of
browser-engine overhead.

> **Status:** Session 11 — Settings and performance optimization.
> ISAI now includes a centralized Settings page, playback/library/cache settings,
> library folder registration, safe cache cleanup, and measured startup/performance
> reporting. Session 12 has not been started.

## Technology stack

| Layer | Technology |
| --- | --- |
| Language | Python 3.12 |
| GUI framework | PySide6 6.12 (Qt 6 Widgets) |
| Audio framework | Qt Multimedia: `QMediaPlayer` + `QAudioOutput`, FFmpeg backend |
| Metadata | Mutagen (tags/artwork) + Qt Multimedia playback metadata fallback |
| Library database | SQLite (`sqlite3`, built-in) |
| Icons | Inline SVG rendered through QtSvg, no icon dependency |
| Target platform | Linux (Zorin OS / Ubuntu), X11 or Wayland |

## Implemented in Session 11 (Settings and performance optimization)

- **Settings page**: centralized Atmospheric settings with Appearance, Playback, Library, Notifications and Linux Integration, Storage and Cache, and About ISAI sections.
- **Playback settings**: default volume, resume playback position, remember playback state, default repeat, default shuffle. Settings persist via QSettings and apply safely without conflicting with the existing AudioEngine/QueueManager.
- **Library settings**: register/remove music folder registrations, rescan registered folders, optional background scan at startup, and library statistics (songs/albums/artists/playlists/favorites). Removing a folder registration does not delete music files.
- **Desktop integration**: track-change notifications, minimize-to-tray close behavior, tray availability, and MPRIS status surfaced in Settings.
- **Storage/cache**: artwork cache location/size, database path/size, clear artwork cache with confirmation, clear ISAI temp files with confirmation. Cache cleanup never deletes music files or the library database.
- **Performance/safety**: library folder table/index in SQLite, safe settings defaults/invalid-value recovery, background scanning preserved, artwork cache clear removes only cache files and clears stale cache artwork paths.

## Implemented in Post-Session 10 (Atmospheric redesign + stabilization)

- **Atmospheric visual identity**: original "ink and ember" dark theme and "warm paper" light theme, both intentionally designed. The UI uses deep/soft layered surfaces, restrained warm accents, editorial typography, subtle gradients, and rounded geometry. It does not imitate Spotify, Apple Music, GNOME/Libadwaita, or generic dashboards.
- **Artwork ambience**: `services/ambient_palette.py` samples artwork at 32×32 on the global Qt thread pool and caches a bounded accent/glow/tint palette. Home, Now Playing, and Mini-Player use these palettes for subtle ambient gradients; no full-image heavy blur is applied.
- **Home redesign**: artwork-led hero with greeting, library stats, recent/favorites shelves, and clear actions. Home uses real library data only.
- **Now Playing redesign**: immersive artwork-led layout, responsive stacked mode for narrow widths, synced lyrics with active-line emphasis, transport controls, queue/lyrics/mini-player access, and artwork-driven ambient background.
- **Seek slider ownership**: the bottom player hides its seek row while Now Playing is active; other pages show the compact bottom seek bar. Both use the same `AudioEngine` position/duration/seek signals — no duplicate playback timer.
- **List readability**: shared `ui/components/track_table.py` applies 54px rows, 38px artwork icons, 40px header, and clearer table styling to Songs, Favorites, Recently Played, Album detail, and Playlist detail. Queue rows use 56px readable rows with artwork, title, artist, and duration.
- **Queue/shuffle fix**: `QueueManager` remains the only playback-order owner. Shuffle shuffles only upcoming items, keeps current/history in place, updates the visible queue immediately, and Next plays the first visible upcoming item. Disabling shuffle restores the intended base order. Manual reorder while shuffled does not destroy the original base order.
- **Playback metadata consistency**: `AudioEngine.open_files/enqueue_files/play_next_files` accept library track records, so queue, MPRIS, notifications, and player surfaces receive consistent title/artist/duration/artwork metadata.
- **Mini-Player redesign**: compact atmospheric mini-player with ambient artwork background, artwork thumbnail, progress, and transport controls, sharing the same AudioEngine.

## Implemented in Session 10

- **MPRIS2**: `services/mpris_service.py` exposes `org.mpris.MediaPlayer2` and `org.mpris.MediaPlayer2.Player` over session D-Bus (QtDBus). Service name: `org.mpris.MediaPlayer2.isai` (falls back to instance-specific name if occupied). Supports play/pause/stop/next/previous/seek/setposition, metadata, volume, playback status, can* properties. Metadata includes title, artist, album, artwork, track id, and `mpris:length`; `PropertiesChanged` is emitted with the exact `sa{sv}as` signature so GNOME Shell and other GDBusProxy clients update the system media control correctly.
- **Notifications**: `services/notification_service.py` sends track-change notifications via `org.freedesktop.Notifications`; dedupes same track, respects setting, fails gracefully.
- **System tray**: `ui/system_tray.py` provides Show/Play-Pause/Next/Previous/Quit and syncs track/status. Close-to-tray behavior configurable.
- **Settings**: Desktop Integration section for notifications and close-to-tray; tray availability shown.
- **Icon/launcher**: SVG/PNG icon assets under `assets/icons/`, `launch.sh`, and dev `isai.desktop`.

## Implemented in Session 9

- **Theme architecture**: centralized `ThemeManager` with Dark/Light/System preferences, effective-theme resolution, QPalette + QSS application, and QSettings persistence (`appearance/theme`, `appearance/reduced_motion`).
- **System theme**: uses Qt color scheme detection when available; falls back safely to Dark when detection is unavailable.
- **Reduced motion**: Settings toggle persists and disables nonessential animations (sidebar width, page fade, mini-player fade).
- **Animations**: subtle sidebar expand/collapse width animation, page fade-in navigation, mini-player fade in/out; offscreen/test-safe guards.
- **Settings UI**: Appearance includes Dark/Light/System (when supported) and Reduce motion.

## Implemented in Session 8

- **Now Playing**: dedicated page with large artwork, track metadata, progress/seek, prev/play/next, shuffle/repeat/favorite, volume, queue access, and lyrics panel.
- **Mini-Player**: compact window reusing the same `AudioEngine`; hides main window on enter, restores on exit/close; no second QMediaPlayer.
- **Local lyrics**: `services/lyrics_service.py` parses standard LRC timestamps, multiple timestamps per line, metadata tags, UTF-8 BOM; lookup order explicit > same-name .lrc > none. Active line syncs to playback position; clicking a lyric seeks.
- **Playback behavior fix**: double-clicking a song in Songs now plays all visible songs starting at the clicked track.

## Implemented in Session 7

- **Queue manager**: `services/queue_manager.py` owns queue items, current index, shuffle, repeat, and stable queue item IDs. Supports add/add-many/play-next/remove/move/clear/skip/next/previous, duplicate tracks, and missing-file-safe operations.
- **Playback integration**: `AudioEngine` remains the only QMediaPlayer owner. Play Now replaces queue, Play Next inserts after current, Add to Queue appends, end-of-track auto-advances by queue/repeat rules.
- **Shuffle/Repeat**: `QueueManager` is the sole owner of playback order. Shuffle keeps the current track/history in place, shuffles only upcoming items, and immediately updates the visible queue. Next plays the first visible upcoming item. Turning shuffle off restores the intended base order. Repeat modes: Off, All, One. Manual Next in Repeat One advances.
- **Queue UI**: Toggleable queue panel with current track, upcoming tracks, play selected, remove, clear, move up/down, and drag-drop reorder. Player bar has shuffle/repeat/queue controls.
- **Keyboard shortcuts**: Space play/pause (disabled while typing), Ctrl+Right/Left next/previous, Ctrl+Up/Down volume, Ctrl+M mute, Ctrl+S shuffle, Ctrl+R repeat, Ctrl+Q queue.
- **Persistence**: SQLite `queue_state` and `queue_items` tables store queue order, current track/path, position, shuffle, repeat. Restore on startup loads paused state; missing files are skipped.

## Implemented in Session 6

- **Playlists**: SQLite `playlists` and `playlist_tracks` tables with safe migration; create/rename/delete playlists; add/remove/reorder tracks; playlist detail view with Play all, add tracks, remove selected, move up/down; persistent ordering.
- **Favorites**: SQLite `favorites` table; add/remove/toggle/check/count/get favorites; player-bar heart button; favorite actions in song/album/playlist context menus; favorite indicator in Songs; Favorites page populated from DB; immediate UI refresh.
- **Playback integration**: play individual playlist/favorite tracks or Play all playlist via existing `AudioEngine` temporary queue; missing files handled gracefully.

## Implemented in Session 5

- **Songs page**: 6-column table (#/Title/Artist/Album/Duration/Format), text elision + tooltips, row selection (single/multi), double-click playback via existing `AudioEngine`, right-click context menu (Play, Add to playback list, Show track information, Open containing folder), debounced search by title/artist/album, sort by Title/Artist/Album/Duration/Date added with ascending/descending toggle, matching-count label, empty-search state.
- **Albums page**: responsive album grid with lazy-loaded/scaled artwork cache, search by album/artist, sort by title/artist/track count with asc/desc, single click opens album detail view with track table and Play album action, double-click plays album.
- **Artists page**: responsive artist grid with elided long names and tooltips, search by artist name, sort by name/track count/album count with asc/desc, click navigates to Songs filtered by artist.
- **Track information dialog**: read-only dialog showing title, artist, album, album artist, track/disc number, genre, year, duration, format, bitrate, file size, file path.
- **Artwork performance**: `AlbumCard` lazy-loads artwork on paint, scales to display size, and caches scaled pixmaps by path/size/mtime with a bounded in-memory cache.
- **AudioEngine**: added `enqueue_files()` for compatible temporary playback-list additions from context menus.

## Implemented in Session 4

- **Persistent library database**: `services/library_database.py` using SQLite in
  the user application data directory (not in source tree).
- **Music scanning**: `services/music_scanner.py` background worker on a QThread.
  Recursive folder scan, individual/multiple file import, progress signals,
  cancellation, and counts for discovered/imported/skipped/failed files.
- **Metadata extraction**: `services/metadata_reader.py` using Mutagen. Extracts
  title, artist, album, album artist, track/disc number, genre, year, duration,
  format, bitrate, file path, file size, mtime, date added. Missing/corrupt
  metadata falls back safely.
- **Artwork cache**: `services/artwork_cache.py` extracts embedded artwork and
  stores files in the user data artwork cache using content hashes; SQLite stores
  only the path.
- **UI integration**: Songs table with search/sort/double-click playback; Albums
  and Artists grids from DB; Home shows Recently Added and real Recently Played
  history; Recently Played page shows actual playback history.
- **Import controls**: File menu actions for **Import Music Folder...** and
  **Import Music Files...**. Existing **Open Audio Files...** remains for
  temporary playback.

## Audio playback (Session 3, preserved)

```text
PlayerBar ── controls ──▶ AudioEngine ──▶ QMediaPlayer ──▶ QAudioOutput ──▶ system audio
    ▲                          │
    └──── state, metadata ─────┘
```

`AudioEngine` remains the single playback source of truth. Double-clicking a
library track loads its file path into the existing engine and starts playback.

## Library architecture

```text
Import action / folder picker
        │
        ▼
MainWindow.start_scan(paths)
        │
        ▼
QThread + MusicScannerWorker
        │  recursive discovery, supported extensions
        ├─▶ MetadataReader (Mutagen) ──▶ normalized track dict
        ├─▶ ArtworkCache (hash files) ──▶ artwork_path
        └─▶ LibraryDatabase (SQLite upsert)
                    │
                    ▼
            MainWindow.refresh_library_views()
                    │
        ┌───────────┼───────────┬──────────────┐
        ▼           ▼           ▼              ▼
     Home       Songs       Albums/Artists  Recently Played
```

## Database

- **Engine**: Python `sqlite3`
- **Default location**: Qt `QStandardPaths.AppDataLocation` / `library.db`
  (typically `~/.local/share/ISAI/library.db` on Linux). Can be overridden by
  passing `library_db` to `MainWindow`/`LibraryDatabase` (used by tests).
- **Artwork cache**: same data dir, `artwork/` subdirectory
  (typically `~/.local/share/ISAI/artwork/`).

### Tracks schema

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | autoincrement |
| file_path | TEXT UNIQUE | canonical path, duplicate protection |
| title | TEXT | filename fallback |
| artist | TEXT | `Unknown Artist` fallback |
| album | TEXT | `Unknown Album` fallback |
| album_artist | TEXT | artist fallback |
| track_number | INTEGER | nullable |
| disc_number | INTEGER | nullable |
| genre | TEXT | |
| year | INTEGER | nullable |
| duration | INTEGER | milliseconds |
| format | TEXT | extension/format |
| bitrate | INTEGER | nullable |
| file_size | INTEGER | bytes |
| file_mtime_ns | INTEGER | change detection |
| date_added | TEXT | ISO UTC |
| artwork_path | TEXT | cached file path, nullable |
| last_played | TEXT | ISO UTC, nullable |

Indexes: `file_path` unique, artist, album+album_artist, title, date_added,
last_played. Bulk imports use transactions/`executemany` where appropriate.

## Supported formats

The scanner/import filter accepts: **MP3, WAV, FLAC, OGG, M4A, AAC**.

Actual playback depends on the installed Qt Multimedia backend codecs. ISAI does
not claim a format is playable unless Qt Multimedia can decode it; unsupported
or damaged files produce clear playback errors.

## Metadata and artwork

- **Extractor**: Mutagen (`mutagen.File`, ID3/MP4/FLAC/Vorbis tag handling).
- **Fallbacks**: missing title -> filename stem; missing artist -> `Unknown Artist`;
  missing album -> `Unknown Album`; missing artwork -> placeholder icon.
- **Artwork**: embedded image bytes extracted when available, stored as hash-named
  files in the artwork cache. Duplicate artwork bytes are deduplicated by SHA-1
  hash. Malformed artwork is ignored safely.

## Duplicate detection / rescan behavior

- `file_path` is UNIQUE in SQLite; imports use upsert.
- Rescans skip unchanged files when file size and mtime ns match existing DB record.
- Changed files have metadata refreshed; `date_added` is preserved.
- No expensive full-file hashing during normal scan; artwork dedupe uses hash of
  embedded artwork bytes only when artwork is present.

## Scan progress UI

The main window shows a scan status bar during imports with: status text,
progress indicator, discovered/imported/skipped/failed counts, current file name,
and Cancel. Scanning runs on a background QThread worker; UI remains responsive.

## Project structure

```text
isai/
├── main.py
├── requirements.txt
├── README.md
├── DEVELOPMENT_LOG.md
├── core/
│   ├── __init__.py
│   └── theme_manager.py
├── services/
│   ├── __init__.py
│   ├── audio_engine.py
│   ├── library_database.py
│   ├── metadata_reader.py
│   ├── artwork_cache.py
│   └── music_scanner.py
├── ui/
│   ├── main_window.py
│   ├── sidebar.py
│   ├── player_bar.py
│   ├── icons.py
│   ├── components/
│   │   ├── album_card.py
│   │   ├── artist_card.py
│   │   ├── card_grid.py
│   │   ├── empty_state.py
│   │   ├── search_field.py
│   │   ├── sort_combo.py
│   │   └── track_info_dialog.py
│   └── pages/
├── assets/
├── data/cache/
└── tests/
    ├── test_smoke.py
    ├── test_ui.py
    ├── test_audio_engine.py
    ├── test_library.py
    ├── test_ui_session5.py
    ├── test_playlists_favorites.py
    ├── test_queue.py
    ├── test_now_playing_lyrics.py
    ├── test_theme_session9.py
    └── test_desktop_integration.py
```

## Environment setup

Requirements: Python 3.10+ (developed on Python 3.12) and a Linux desktop.

```bash
cd ~/Projects/isai/isai
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> This working copy also has a prepared environment: `source ../.isai/bin/activate`.

## Run from source

```bash
cd ~/Projects/isai/isai
source ../.isai/bin/activate
python main.py
```

## Tests

```bash
cd ~/Projects/isai/isai
source ../.isai/bin/activate
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
python -m pip check
```

The automated suite covers smoke/UI, audio engine, queue, library/DB/scanning, playlists/favorites, lyrics, theme/desktop integration, settings, and equalizer. The most recent full run in this environment: **150 tests, 149 passed, 1 failure before fix** (`test_ui.TestWindow` PAGE_KEYS updated for Equalizer page), then fixed; the two updated tests pass.

## Packaging (Session 12)

Build artifacts are generated under `dist/` (ignored by git). Packaging configs/scripts live under `packaging/`.

### Prerequisites

```bash
cd ~/Projects/isai/isai
source ../.isai/bin/activate
python -m pip install -r requirements.txt
python -m pip install pyinstaller
```

System tools used: `dpkg-deb`, `patchelf`, `desktop-file-validate`, `curl`/`wget`, `appimagetool` (downloaded to `packaging/tools/`).

### Build PyInstaller standalone

```bash
cd ~/Projects/isai/isai
./packaging/scripts/build_pyinstaller.sh
# Output: dist/isai/
```

### Build Debian package

```bash
cd ~/Projects/isai/isai
./packaging/scripts/build_deb.sh
# Output: dist/packages/isai_<version>_amd64.deb
```

### Build AppImage

```bash
cd ~/Projects/isai/isai
./packaging/scripts/build_appimage.sh
# Output: dist/packages/ISAI-<version>-x86_64.AppImage
```

### Build all

```bash
cd ~/Projects/isai/isai
./packaging/scripts/build_all.sh
```

### Clean build artifacts

```bash
cd ~/Projects/isai/isai
./packaging/scripts/clean.sh
```

## Installation

### Debian package

```bash
sudo apt install ./dist/packages/isai_0.9.0_amd64.deb
# or
sudo dpkg -i ./dist/packages/isai_0.9.0_amd64.deb
```

Launch from the Zorin/desktop application menu as **ISAI**, or run:

```bash
isai
```

Uninstall:

```bash
sudo apt remove isai
```

Uninstall does **not** delete your personal music files, library database, settings, playlists, favorites, history, or artwork cache.

### AppImage

```bash
chmod +x ./dist/packages/ISAI-0.9.0-x86_64.AppImage
./dist/packages/ISAI-0.9.0-x86_64.AppImage
```

Optional desktop integration can be done with AppImageLauncher or by manually creating a desktop entry; ISAI does not claim automatic AppImage menu integration.

## User data locations

ISAI stores user data in standard Linux user locations (actual paths used by the app):

- **Library database**: `~/.local/share/ISAI/library.db`
- **Artwork cache**: `~/.local/share/ISAI/artwork/`
- **Settings (QSettings INI)**: `~/.config/ISAI/ISAI.ini`
- **Qt cache/config**: may be created under standard Qt user dirs as needed

Packaged builds must **not** include personal music, databases, playlists, favorites, queue/history, settings, or caches. Upgrades should preserve existing user data.

## Known limitations

- GNOME Shell 46 built-in media control has no seek slider; MPRIS exposes seek/position for clients that support it.
- PyInstaller onedir build is large because it bundles PySide6/Qt; trimming should be done carefully to avoid missing Qt Multimedia/plugins.
- EQ pipeline uses QAudioBufferOutput -> C biquad DSP -> QAudioSink. It is real audio processing, but format/device edge cases may exist; manual desktop audio verification is required.
- Packaged AppImage/deb behavior should be verified on clean Zorin/Ubuntu environments; this dev session cannot fully replace clean-system manual QA.

## Roadmap

Sessions 1-11 delivered foundation, UI, playback, library, playlists/favorites, queue, lyrics, theme/desktop integration, settings, and equalizer. Session 12 adds packaging/distribution. Session 13 is final installation & verification on Zorin OS and begins only after approval.
