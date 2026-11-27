# ISAI — Development Log

## Session 1 — Project Foundation

**Date:** 2026-11-25
**Goal:** Establish the project skeleton, environment, and a minimal, correctly
shutting-down PySide6 application. No player features yet.

### Progress

- Inspected the development environment (Python, venv, Git, PySide6, Qt Multimedia).
- Created the project directory structure.
- Installed PySide6 into the existing virtual environment (no system packages).
- Implemented a minimal `QApplication` + `QMainWindow` shell.
- Added automated smoke tests covering imports, structure, window configuration,
  event-loop startup, and graceful shutdown.
- Documented setup and run instructions.

### Files created

| File | Purpose |
| --- | --- |
| `main.py` | Application entry point and minimal main window |
| `requirements.txt` | Runtime dependency pin (`PySide6==6.12.0`) |
| `README.md` | Project overview, stack, structure, setup, install, run |
| `DEVELOPMENT_LOG.md` | This log |
| `.gitignore` | Python, venv, tooling, build, and cache ignores |
| `core/__init__.py` | Core package placeholder |
| `ui/__init__.py` | UI package placeholder |
| `services/__init__.py` | Services package placeholder |
| `assets/icons/.gitkeep` | Placeholder for icons |
| `assets/images/.gitkeep` | Placeholder for images |
| `assets/fonts/.gitkeep` | Placeholder for fonts |
| `assets/styles/.gitkeep` | Placeholder for stylesheets |
| `data/cache/.gitkeep` | Placeholder for runtime cache |
| `tests/test_smoke.py` | Session 1 smoke tests (`unittest`, no extra deps) |

Directories `tests/` and `data/cache/` are present; the cache contents are
git-ignored while `.gitkeep` keeps the directory in the repository.

### Environment

- Python: 3.12.3 (`/usr/bin/python3.12`)
- Virtual environment: `/home/niranjnr/projects/isai/.isai` (active)
- Git: 2.56.1
- PySide6: 6.12.0 (Qt 6.12.0, Shiboken 6.12.0)
- Qt Multimedia: available; FFmpeg 9.0.1 backend; PulseAudio output detected
  (`Built-in Audio Analog Stereo`)
- Platform: Zorin OS (Ubuntu-based), X11 session

### Dependencies

Installed into the virtual environment only:

```text
PySide6==6.12.0
├── PySide6_Essentials==6.12.0
├── PySide6_Addons==6.12.0
├── PySide6_Pdf==6.12.0.140
├── PySide6_WebEngine==6.12.0.140
└── shiboken6==6.12.0
```

No system packages were installed and `sudo` was not used.

### Tests performed

Command:

```bash
python -m unittest discover -s tests -v
```

Cases:

1. PySide6 / QtCore / QtWidgets imports.
2. Qt Multimedia imports plus `QMediaPlayer`/`QAudioOutput` construction.
3. Required project structure.
4. Main-window title, default size, and central-widget content.
5. Event loop starts and exits with code `0` (`QTimer`-driven quit).

### Test results

`Ran 5 tests ... OK` — all 5 tests pass (headless `offscreen` platform).

Additional manual checks:

- Real X11 launch: window created and event loop exited cleanly with code `0`.
- `git status` inspected; no commit made (awaiting approval).

### Known issues

- The prepared virtual environment is named `.isai` (at the repository root),
  not `.venv`. It is used as-is and ignored by Git; `README.md` documents both.
- The Git repository root is one level above the project folder, so changes
  appear under the `isai/` subtree.
- Qt Multimedia is verified at the import/object level only; audio playback is
  intentionally not implemented in this session.
- No application icon, desktop entry, or keyboard shortcuts yet (later sessions).
- `requirements.txt` pins PySide6 exactly; revisit when a newer release is
  deliberately adopted.

### Next session objectives

- Begin Session 2 (music library foundation) once Session 1 is approved.
- No Session 2+ code has been written in this session.

---

## Session 2 — Main UI and Linux-Native Design

**Date:** 2026-11-25
**Goal:** Turn the foundation window into a polished, navigable music-player
interface shell with reusable components and a centralized theme system. No
audio playback or library features.

### Progress

- Built the three-area layout: collapsible sidebar, page stack, persistent
  bottom player bar.
- Added eight pages (Home, Songs, Albums, Artists, Playlists, Favorites,
  Recently Played, Settings) with consistent headers and intentional empty
  states.
- Implemented working navigation, including Home "View all" links and an
  exclusive selected state in the sidebar.
- Implemented automatic sidebar collapse below 1000 px, plus a manual toggle.
- Added a dark and light theme with runtime switching, a matching `QPalette`,
  theme-aware SVG icons, and `QSettings` persistence.
- Added reusable components: `PageHeader`, `EmptyState`, `SearchField`,
  `SectionHeader`, `AlbumCard`, `ArtistCard`, `CardGrid`, and `SortComboBox`.
- Added a disabled, clearly labelled player bar that remains visible across all
  pages.
- Added Session 2 UI tests and visually checked dark/light and narrow layouts.

### Files created

| File | Purpose |
| --- | --- |
| `core/theme_manager.py` | Tokens, QSS template, palette, persistence, theme signal |
| `ui/main_window.py` | Window assembly, navigation, theme refresh, responsiveness |
| `ui/sidebar.py` | Sidebar, `NavigationItem`, collapse behavior |
| `ui/player_bar.py` | Persistent no-track player bar |
| `ui/icons.py` | Inline symbolic SVG icon set with caching |
| `ui/components/page_header.py` | Consistent page heading |
| `ui/components/empty_state.py` | Reusable empty-state panel |
| `ui/components/search_field.py` | Themed search input |
| `ui/components/section_header.py` | Section heading with optional action |
| `ui/components/album_card.py` | Reusable album tile |
| `ui/components/artist_card.py` | Reusable artist tile |
| `ui/components/card_grid.py` | Responsive card grid |
| `ui/components/sort_combo.py` | Combo box with themed chevron |
| `ui/pages/base_page.py` | Scrollable page scaffold |
| `ui/pages/home_page.py` | Welcome and library shelves |
| `ui/pages/songs_page.py` | Search, sort, empty library |
| `ui/pages/albums_page.py` | Album grid area and empty state |
| `ui/pages/artists_page.py` | Artist grid area and empty state |
| `ui/pages/playlists_page.py` | Create-playlist entry point and empty state |
| `ui/pages/favorites_page.py` | Favorites empty state |
| `ui/pages/recently_played_page.py` | Listening-history empty state |
| `ui/pages/settings_page.py` | Appearance, palette preview, app information |
| `ui/pages/__init__.py` | Page exports |
| `tests/test_ui.py` | Navigation, theme, layout, and content tests |

### Files modified

- `main.py` — now creates the theme manager, applies the saved theme, centers
  the main window, and launches `ui.main_window.MainWindow`.
- `core/__init__.py` — added `__version__ = "0.2.0"`.
- `tests/test_smoke.py` — updated the Session 1 window test for the new shell
  and extended the structure checks.
- `README.md` — new architecture, theme system, run, and test documentation.
- `DEVELOPMENT_LOG.md` — this Session 2 entry.

`requirements.txt` is unchanged: PySide6 remains the only dependency (QtSvg is
part of PySide6 Essentials).

### UI architecture

```text
QMainWindow
└── appRoot (QVBoxLayout)
    ├── body (QHBoxLayout)
    │   ├── Sidebar (expanded 232 px / collapsed 68 px)
    │   └── contentArea
    │       └── QStackedWidget (8 scrollable pages)
    └── PlayerBar (88 px, persistent)
```

- `MainWindow` owns navigation and connects the sidebar signal to the page
  stack. The player bar is a sibling of the page stack, never a page.
- Pages derive from `BasePage`, a scroll area with a header and a content
  column. Horizontal scrolling is disabled; content reflows with the window.
- Empty states explain that importing music and playback belong to future
  sessions. No fake songs, albums, artists, or playback data are generated.
- `CardGrid` reflows album/artist cards by available width for future data.
- At widths below 1000 px the sidebar auto-collapses; manual toggle state is
  kept until the width crosses that threshold again.

### Theme implementation

- `ThemeColors` defines 19 named tokens for each palette in
  `core/theme_manager.py`; there is one `Template`-based QSS for the entire app.
- `ThemeManager.apply()` sets both the application palette and style sheet.
- Theme changes emit `theme_changed`; `MainWindow` walks themed widgets and
  refreshes symbolic icons and settings previews without a restart.
- The selected theme is stored under `appearance/theme` using a user-scoped
  INI `QSettings` store (`~/.config/ISAI/ISAI.ini`) and loaded before the
  window is shown.
- Settings exposes Light/Dark buttons, a live palette preview, and the app
  version, PySide6/Qt versions, and platform.

### Tests performed

```bash
python -m unittest discover -s tests -v
python3 -m compileall -q main.py core ui tests
python3 -m pip check
```

Automated coverage:

1. Session 1 environment, structure, startup/shutdown tests (updated).
2. All eight pages created with correct headings and stack entries.
3. Sidebar clicks switch pages, keep exactly one selected item, and leave the
   player bar visible.
4. Home "View all" actions navigate to the intended pages.
5. Manual collapse/expand and automatic collapse at 900 px, expansion at
   1200 px; collapsed items keep icons and tooltips.
6. Dark/light switching updates the application style sheet immediately.
7. Theme choice persists across a reloaded `ThemeManager` and is applied on a
   new window.
8. Settings buttons switch the theme, sync the checked state, and save it.
9. Invalid theme names are rejected.
10. Player bar controls are disabled, show "No track playing", and display
    0:00/0:00.
11. Empty states exist on all content pages; no fake album/artist cards.
12. Every built-in icon renders; version metadata is present.

### Test results

```text
Ran 22 tests in 23.143s

OK
```

- `compileall`: OK.
- `pip check`: `No broken requirements found.`
- Real X11 launch: window opened at 1200×736 (the window manager clamped the
  760 px request to the available desktop height), minimum 850×550 was
  reported, player bar was visible, sidebar collapse worked, and the event loop
  exited with code 0.
- Visual checks at 1200×760, 900×600, and 850×550 in both dark and light themes;
  no horizontal overflow or clipped player controls observed.

### Known issues

- Audio playback, music importing, scanning, metadata, SQLite, and real
  playlists are intentionally not implemented. All playback controls and
  "Create playlist" are disabled.
- Search and sorting are present but not wired to data because no library
  exists yet.
- Album and artist grids are empty by design; no placeholder media is shown.
- Reapplying the full style sheet on theme change takes a fraction of a second
  under the offscreen test platform; this is acceptable but can be optimized
  later if needed.
- A manual sidebar toggle at a narrow width persists until the window crosses
  the 1000 px threshold again.
- No application icon, desktop entry, keyboard shortcuts, MPRIS, tray, or
  packaging yet.
- The prepared environment remains `.isai` one directory above the project.
  `.venv` is documented for fresh clones.

### Next session objectives

- Begin Session 3 on approval, following the project plan.
- No Session 3 code has been written in this session.

---

## Session 3 — Real Audio Playback

**Date:** 2026-11-25
**Goal:** Replace the disabled player-bar shell with real local audio playback
using Qt Multimedia, while keeping the Session 2 interface and layout intact.

### Progress

- Added `services/audio_engine.py`, an `AudioEngine` QObject around
  `QMediaPlayer` and `QAudioOutput`.
- Added a native **File → Open Audio Files…** action with `Ctrl+O`; multiple
  selected files join a temporary in-memory track list.
- Implemented load, play, pause, stop, previous, next, automatic advance at the
  end of a track, seeking, volume, and mute.
- Wired the existing player bar to the engine: play/pause icon and tooltip,
  live progress, drag-to-seek, elapsed/total time, volume slider, and mute
  button.
- Added filename fallback plus Qt Multimedia title/artist metadata. No Mutagen
  dependency was needed.
- Added clear, non-blocking error messages for missing, unsupported, or
  undecodable files.
- Added a `volume-muted` symbolic icon and an error color state in the theme.
- Preserved theme switching and page navigation during playback.
- Added Session 3 engine and player-bar integration tests.
- Verified every requested format with real files generated through FFmpeg.

### Files created

| File | Purpose |
| --- | --- |
| `services/audio_engine.py` | Qt Multimedia playback, temporary track list, metadata, signals |
| `tests/test_audio_engine.py` | Construction, validation, loading, playback, queue, volume, error tests |

### Files modified

- `ui/player_bar.py` — replaced the disabled shell with engine-backed controls,
  track text, progress, seeking, volume, mute, and inline error display.
- `ui/main_window.py` — owns the `AudioEngine`, adds the File menu and native
  open dialog, and exposes `load_audio_files()` for tests.
- `ui/icons.py` — added the `volume-muted` icon.
- `core/theme_manager.py` — added the player-bar error color rule.
- `core/__init__.py` — version bumped to `0.3.0`.
- `tests/test_ui.py` — updated the no-track assertions and added player-bar
  integration tests.
- `README.md` — Session 3 status, playback architecture, formats, controls, and
  test documentation.
- `DEVELOPMENT_LOG.md` — this entry.

`requirements.txt` is unchanged: PySide6 remains the only dependency.

### Playback architecture

```text
PlayerBar ── controls ──▶ AudioEngine ──▶ QMediaPlayer ──▶ QAudioOutput ──▶ system audio
    ▲                          │
    └──── state, metadata ─────┘
```

`AudioEngine` owns the player, audio output, temporary queue, and all state. It
exposes plain methods and Qt signals; `PlayerBar` only renders state and sends
user intent back. Playback therefore continues independently of the current
page and survives theme changes.

Signals:

- `state_changed(str)` — `stopped`, `playing`, or `paused`.
- `position_changed(int)` and `duration_changed(int)` — milliseconds.
- `track_changed(object)` — `TrackInfo` or `None`.
- `queue_changed()` — temporary queue membership/index changed.
- `volume_changed(int)` and `muted_changed(bool)`.
- `error_occurred(str)` — human-readable message.

The player bar keeps its 88 px layout. Play, previous, next, and progress are
disabled without a track; volume and mute are available immediately. Queue,
favorites, and expansion remain disabled because they are outside Session 3.

### Formats verified

Generated with system FFmpeg 6.1.1; decoded through Qt Multimedia's bundled
FFmpeg 9.0.1 backend.

| Format | File | Duration reported | Played | Position advanced |
| --- | --- | --- | --- | --- |
| PCM WAV | `tone.wav` | 2000 ms | Yes | Yes |
| MP3 | `tone.mp3` | 2000 ms | Yes | Yes |
| FLAC | `tone.flac` | 2000 ms | Yes | Yes |
| Ogg Vorbis | `tone.ogg` | 2000 ms | Yes | Yes |
| MPEG-4 AAC | `tone.m4a` | 2000 ms | Yes | Yes |
| AAC (ADTS) | `tone.aac` | 2016 ms | Yes | Yes |

A tagged MP3 reported title `Tone Title` and artist `ISAI Test`, confirming the
Qt metadata path. Untagged files fall back to the filename stem and
`Unknown artist`.

### Tests performed

```bash
python -m unittest discover -s tests -v
python3 -m compileall -q main.py core ui services tests
python3 -m pip check
```

Automated coverage added in Session 3:

1. Engine construction, initial state, defaults, and supported extensions.
2. Track info fallback to filename and unknown artist.
3. Volume clamping, volume signals, mute toggling, and idempotent setters.
4. Missing and unsupported files rejected with meaningful errors, including
   mixed selections where valid files still load.
5. Empty selections and duplicate path handling.
6. WAV loading, duration reporting, filename metadata, and track signals.
7. Invalid audio files report an error and leave the engine stopped.
8. Next/previous navigation, boundary behavior, and empty-queue errors.
9. Real play/pause/stop with generated WAV files and advancing position.
10. Seeking, position clamping, and pause stability.
11. Playing without a track reports an error.
12. Player-bar title/artist, duration, button enablement, queue disabled state.
13. Player-bar play/pause tooltip and live progress.
14. Drag-to-seek signal path updates the engine and time label.
15. Volume slider and mute button drive the engine and update tooltips.
16. File menu exposes Open and Quit with shortcuts.
17. The File → Open wrapper passes the dialog selection to the engine and loads
    the chosen track.

Automated playback uses generated WAV tones at zero volume, so the suite is
silent while still exercising the real Qt Multimedia pipeline. The audible
check remains a separate manual step.

### Test results

```text
Ran 45 tests in 31.424s

OK
```

- `compileall`: OK.
- `pip check`: `No broken requirements found.`
- Real X11 launch (`DISPLAY=:0`): window opened at 1200×736 (window manager
  clamp), player bar visible, File menu present.
- Screenshots inspected in dark and light themes and at 900×600; sidebar
  auto-collapsed correctly, player controls remained visible, and no horizontal
  overflow was observed.
- Loaded a tagged MP3 through the real application: title `Tone Title`, artist
  `ISAI Test`, duration `0:02`, playing state, live progress, drag-to-seek to
  0:03 of a 6-second test file, volume 40, mute/unmute, and navigation through
  Songs/Albums/Artists/Settings while playback continued.
- When the 2-second test track ended, the engine returned to `stopped`, held
  the last track loaded, and allowed replay.

### Audio output verification

The environment is automated and cannot confirm what a human hears. To verify
that playback was not merely a simulated clock:

- Qt reported `PlayingState` and the position advanced in real time.
- `pactl list sink-inputs` showed a live Qt stream while playback ran:
  `s16le 2ch 44100Hz`, `Corked: no`, connected to the hardware sink
  (`Built-in Audio Analog Stereo`).
- The sink moved from `SUSPENDED` to `RUNNING` during playback.

This confirms a live output stream reached the system audio server. A final
human listening check is still recommended on the target desktop.

### Known issues

- No persistent queue, library scanning, playlist persistence, shuffle, repeat,
  lyrics, MPRIS, tray integration, notifications, streaming, or packaging.
- Queue, favorites, and expanded-player controls remain disabled by design.
- Metadata is limited to title and artist; album art is not displayed yet.
- Format support depends on the installed Qt Multimedia/FFmpeg backend. Files
  with a listed extension that cannot be decoded show an error.
- Error messages temporarily replace the artist line for six seconds; there is
  no separate status-bar history.
- Only `Ctrl+O` (open) and `Ctrl+Q` (quit) have shortcuts; there is no
  space-to-play/pause shortcut yet.
- Playback stops at the end of the temporary queue; it does not loop.
- If no audio output device exists, Play reports a clear error instead of
  failing silently.

### Next session objectives

- Stop after Session 3 and await approval.
- No Session 4 code has been written in this session.


---

## Session 4 — Music Library, Folder Scanning and Metadata

### Summary

Added a persistent local music library backed by SQLite, background folder/file
scanning, Mutagen metadata extraction, embedded artwork caching, and library UI
integration. Existing Session 1-3 behavior was preserved; all 63 automated tests
pass.

### Features implemented

- **SQLite library database** (`services/library_database.py`): creates DB in Qt
  `QStandardPaths.AppDataLocation` (default `~/.local/share/ISAI/library.db`),
  tracks schema with unique `file_path`, indexes, parameterized queries,
  add/get/update/remove/upsert, search, recently added/played, album/artist
  summaries, `mark_played`, and lightweight migration for `file_mtime_ns`/`last_played`.
- **Metadata extraction** (`services/metadata_reader.py`): Mutagen-based
  extraction for title, artist, album, album_artist, track/disc number, genre,
  year, duration, format, bitrate, file size, mtime, date added. Safe fallbacks:
  title=filename stem, artist=`Unknown Artist`, album=`Unknown Album`.
- **Artwork cache** (`services/artwork_cache.py`): extracts embedded artwork bytes,
  stores by SHA-1 content hash in `~/.local/share/ISAI/artwork/` (or DB-adjacent
  artwork dir), deduplicates, ignores malformed artwork. SQLite stores path only.
- **Background scanner** (`services/music_scanner.py`): `MusicScannerWorker`
  QObject moved to QThread; recursive discovery; supported extensions
  `.mp3/.wav/.flac/.ogg/.m4a/.aac`; import files/folders; cancellation flag;
  progress/finished/error signals; discovered/imported/skipped/failed counts;
  skips unchanged files by size+mtime; upserts changed files while preserving
  `date_added`.
- **UI integration**:
  - File menu: **Import Music Folder...**, **Import Music Files...**; existing
    Open Audio Files retained for temporary playback.
  - Scan status bar with progress, counts, current file, cancel, completion message.
  - **Songs**: table (Title/Artist/Album/Duration/Format), search, sort,
    double-click plays selected track via existing AudioEngine.
  - **Albums**: grid grouped by album+album_artist, artwork where available,
    click plays album tracks.
  - **Artists**: grid from DB, click filters/navigates to Songs.
  - **Home**: Recently Added and real Recently Played (from DB `last_played`);
    Favorites remains empty state (no persistence).
  - **Recently Played**: real history from DB.
- **Playback integration**: MainWindow marks played tracks in DB on track change;
  AudioEngine remains sole playback source.

### Files created

- `services/library_database.py`
- `services/metadata_reader.py`
- `services/artwork_cache.py`
- `services/music_scanner.py`
- `tests/test_library.py`

### Files modified

- `core/__init__.py` (version 0.4.0)
- `requirements.txt` (added `mutagen==1.47.0`)
- `ui/main_window.py` (DB ownership, import actions, scan thread/progress, library refresh)
- `ui/pages/songs_page.py`, `albums_page.py`, `artists_page.py`, `home_page.py`, `recently_played_page.py`
- `ui/components/album_card.py`, `artist_card.py`, `empty_state.py`
- `core/theme_manager.py` (table/list/scan status styles)
- `tests/test_smoke.py`, `tests/test_ui.py` (temp DB isolation, version/path updates)
- `README.md`, `DEVELOPMENT_LOG.md`

### Database schema

Tracks table: `id, file_path UNIQUE, title, artist, album, album_artist,
track_number, disc_number, genre, year, duration, format, bitrate, file_size,
file_mtime_ns, date_added, artwork_path, last_played`. Indexes on artist, album+album_artist,
title, date_added, last_played. No separate artists/albums tables; summaries
computed by SQL grouping.

### Test results

Commands run (from `/home/niranjnr/projects/isai/isai`, venv `../.isai/bin/python`):

```bash
QT_QPA_PLATFORM=offscreen ../.isai/bin/python -m unittest discover -s tests -v
../.isai/bin/python -m pip check
../.isai/bin/python -m py_compile main.py core/__init__.py core/theme_manager.py services/*.py ui/main_window.py ui/player_bar.py ui/sidebar.py ui/icons.py ui/pages/*.py ui/components/*.py tests/*.py
```

Results:

- `unittest discover -s tests -v`: **Ran 63 tests in 56.043s — OK**
- `pip check`: **No broken requirements found.**
- `py_compile`: **pass** (no output/errors).

New Session 4 tests cover DB init/CRUD/duplicate protection/persistence/search,
metadata extraction/fallbacks/supported extensions/malformed files, artwork cache
store/dedupe/resolve, recursive scanning, missing/unreadable files, unchanged
rescan skip, QThread background scanning, and library-to-AudioEngine integration.

### Known limitations

- No persistent playlists, favorites persistence, persistent queue, shuffle/repeat,
  lyrics, MPRIS, tray, notifications, online services/artwork, packaging.
- Songs table uses QTableWidget; very large libraries may benefit from model/view
  virtualization later.
- Recently played depends on tracks played in ISAI; no external play history import.
- Missing-file cleanup on startup is not automatic.
- Playback support depends on Qt Multimedia codecs; scanner accepts supported
  extensions but cannot guarantee decode/playback for every file.
- Scan errors are counted and surfaced in status/tooltip; no detailed error log UI.

### Manual verification

No live audible/manual desktop GUI verification was performed in this automated
session. Automated Qt offscreen tests and integration checks passed. Manual
desktop checks are recommended before release.


---

## Session 5 — Library UI Enhancement

### Summary

Enhanced Songs, Albums, and Artists pages with better layouts, search/sort,
context menus, track info dialog, album detail navigation, and artwork loading
improvements. Preserved Session 1-4 functionality and did not modify the user's
existing library/database.

### Files created

- `ui/components/track_info_dialog.py` — read-only track metadata dialog.
- `tests/test_ui_session5.py` — Session 5 UI tests.

### Files modified

- `ui/pages/songs_page.py` — 6-column table, debounce search, asc/desc sort,
  multi-selection, context menu, track info, open containing folder, enqueue.
- `ui/pages/albums_page.py` — search/sort, album detail view, play album, detail
  context menu, double-click play.
- `ui/pages/artists_page.py` — search/sort, count labels, long-name elision support.
- `ui/components/album_card.py` — lazy scaled artwork cache, elision, double-click.
- `ui/components/artist_card.py` — text elision/tooltips.
- `services/library_database.py` — descending sort support; album/artist query+sort.
- `services/audio_engine.py` — `enqueue_files()` for temporary playback list.
- `core/theme_manager.py` — styles for sort direction button, secondary button, menus.
- `README.md`, `DEVELOPMENT_LOG.md`.

### Tests

```bash
QT_QPA_PLATFORM=offscreen ../.isai/bin/python -m unittest discover -s tests -v
../.isai/bin/python -m pip check
../.isai/bin/python -m py_compile ...
```

Results:

- `unittest discover -s tests -v`: **Ran 79 tests in 113.282s — OK**
- `pip check`: **No broken requirements found.**
- `py_compile`: **OK**

### Known limitations

- Songs table still uses `QTableWidget` (acceptable for current scope; very large libraries may benefit from a model/view later).
- Artwork lazy loading is paint-driven with bounded scaled pixmap cache; it is not a full async image pipeline.
- Album single-click opens detail; double-click plays (single-click may fire before double-click).
- No persistent playlists/favorites/queue/shuffle/repeat/lyrics/MPRIS/tray/notifications/packaging.

### Manual verification

No live desktop/manual verification performed in this automated session; recommend
manual checks on Zorin OS desktop.

## Session 7 - Queue management and advanced playback

### Summary
- Added `services/queue_manager.py` with stable queue item IDs, current index, original-order tracking, shuffle, repeat modes, and queue operations (add/add-many/play-next/remove/move/clear/skip/next/previous/restore).
- Reworked `services/audio_engine.py` to remain the single QMediaPlayer owner while delegating queue order/state to `QueueManager`. Added `play_next_files`, `skip_to_queue_id`, and autoplay-aware current-track loading.
- Added queue panel UI (`ui/components/queue_panel.py`) with current/upcoming tracks, play/remove/clear/move up/down and internal drag-drop reorder.
- Updated player bar with shuffle, repeat, and queue toggle controls; updated context menus in Songs/Albums/Playlists/Favorites for Play Now/Play Next/Add to Queue.
- Added keyboard shortcuts via `QShortcut` in `MainWindow`, with Space ignored while text inputs are focused.
- Added SQLite queue persistence tables (`queue_state`, `queue_items`) and save/load/restore methods. Startup restores queue paused; missing files are skipped.
- Fixed regressions: queue track-id FK normalization, theme token `$selected` -> `$accent_subtle`, play button object name styling, and tooltip test expectations.

### Tests
- Targeted: `tests.test_ui`, `tests.test_queue`, `tests.test_playlists_favorites` — 45 tests, OK (after fixes).
- Full suite: run with `QT_QPA_PLATFORM=offscreen ../.isai/bin/python -m unittest discover -s tests -v` (see final report for actual result).

## Session 8 - Now Playing, Mini-Player, and Lyrics

### Summary
- Added `ui/pages/now_playing_page.py` with large artwork, metadata, seek/progress, transport, shuffle/repeat/favorite, volume, queue/lyrics toggles, and LRC open.
- Added `ui/mini_player.py` compact window sharing the existing `AudioEngine`; main window hides on mini-player entry and restores on exit/close.
- Added `services/lyrics_service.py` for local .lrc parsing (timestamps, multiple timestamps, metadata tags, UTF-8 BOM), lookup, and active-line calculation.
- Wired Now Playing into sidebar/navigation and player-bar track click; added Mini Player menu action.
- Fixed Songs double-click behavior to queue all visible songs starting at the clicked track (`AudioEngine.open_files` now supports `start_index`).

### Tests
- Added `tests/test_now_playing_lyrics.py` (lyrics parsing/lookup/active line, Now Playing metadata/lyrics, mini-player open/restore, Songs visible-list queue).
- Full suite: `QT_QPA_PLATFORM=offscreen ../.isai/bin/python -m unittest discover -s tests -v` (see final report for actual result).

## Session 9 - Animations and Themes

### Summary
- Extended `core/theme_manager.py` with `SYSTEM` theme preference, effective theme resolution, Qt color-scheme detection/fallback, and persisted reduced-motion setting.
- Updated Settings page with Dark/Light/System (when supported) and Reduce motion controls.
- Added subtle animations: sidebar width animation, page fade-in on navigation, mini-player fade in/out. Animations respect reduced motion and offscreen mode.
- Added small visual polish: button focus border in QSS.

### Tests
- Added `tests/test_theme_session9.py` (reduced motion persistence, system theme setting/fallback, theme switch during playback).
- Full suite: `QT_QPA_PLATFORM=offscreen ../.isai/bin/python -m unittest discover -s tests -v` (see final report for actual result).

## Session 10 - Linux Desktop Integration

### Summary
- Added MPRIS2 service (`services/mpris_service.py`) using PySide6 QtDBus, exposing root and Player interfaces on session bus. Delegates all actions to existing AudioEngine/QueueManager.
- Added desktop notification service (`services/notification_service.py`) via org.freedesktop.Notifications, with dedupe and setting.
- Added system tray (`ui/system_tray.py`) with playback controls and show/quit; close-to-tray behavior configurable.
- Extended Settings with Desktop Integration controls; persisted via existing QSettings.
- Added app icon assets, launch.sh, and dev isai.desktop.

### Tests
- Added `tests/test_desktop_integration.py`.
- Full suite: `QT_QPA_PLATFORM=offscreen ../.isai/bin/python -m unittest discover -s tests -v` (see final report for actual result).

## Session 10 follow-up - MPRIS metadata / system media control fix

### Problem
GNOME Shell's media control showed "Unknown title" / "Unknown artist" and no
duration information while ISAI was playing.

### Root cause
Two independent D-Bus marshalling bugs in `services/mpris_service.py`:

1. **Metadata values were double-wrapped.** The `Metadata` property returned a
   `QVariantMap` whose values were already `QDBusVariant`, so QtDBus wrapped
   them again (`v v s`, `v v as`). GNOME's `deepUnpack()` then received a
   variant instead of a string and rejected the fields as faulty.
2. **`PropertiesChanged` had the wrong signature.** Passing a plain Python `[]`
   for the invalidated-properties argument made PySide6 infer `av`, producing
   `(sa{sv}av)` instead of the required `(sa{sv}as)`. `GDBusProxy` dropped the
   entire signal, so the system media control never refreshed after startup.

### Fix
- `metadata()` now returns plain D-Bus values (title, artist list, album,
  artwork URI, track id, URL, and `mpris:length` from engine/queue duration).
  QtDBus wraps each value exactly once for both the property getter and
  `PropertiesChanged`.
- `_emit_props()` keeps real values plain and builds an explicitly typed empty
  `as` array with `QDBusArgument` for the third signal argument. That hint makes
  QtDBus infer `a{sv}` for the changed-properties map without any dummy keys.
- Added regression tests for plain metadata values, `mpris:length`/album
  presence, and the typed invalidated-properties argument.

### Verification
- `gdbus call ... Properties.Get ... Metadata` now returns single variants
  (`<'title'>`, not `<<'title'>>`).
- `busctl --user monitor` confirms `PropertiesChanged` signature `sa{sv}as`.
- Live ISAI + GNOME Shell 46 screenshot: system media control shows the correct
  title, artist, and album art; no "faulty metadata" / signature warnings in the
  user journal.

### Note on the seek bar
GNOME Shell 46's media control source only creates Previous / Play-Pause / Next
buttons; it has no progress slider. ISAI's own mini-player and main player bar
already provide seek sliders. MPRIS exposes `Position`, `CanSeek`, `Seek`,
`SetPosition`, `Seeked`, and `mpris:length` for clients that render progress.

## Post-Session 10 - Atmospheric redesign and playback/queue stabilization

### Summary
- Replaced the previous neutral/blue visual direction with an original Atmospheric identity: "ink and ember" dark theme and "warm paper" light theme, both intentionally designed.
- Added `services/ambient_palette.py` for cached, thread-pool artwork sampling (32×32) and restrained accent/glow/tint extraction. Home, Now Playing, and Mini-Player use subtle ambient gradients derived from artwork.
- Redesigned Home into an artwork-led editorial surface with real-library hero, stats, and recent/added/favorites shelves. No fake recommendations or dashboard cards.
- Redesigned Now Playing as an immersive artwork-led page with responsive layout, synced lyrics, and ambient background. Bottom player hides its seek row while Now Playing is active; other pages show the compact seek row. Both use the same `AudioEngine` position/duration/seek signals.
- Redesigned the bottom player, queue panel, mini-player, and shared track tables. Song/queue rows now use 48–56px comfortable heights, 36–44px artwork, and clearer typography.
- Fixed shuffle/queue synchronization. `QueueManager` remains the only playback-order owner. Shuffle preserves current/history, shuffles only upcoming items, updates the visible queue immediately, and Next plays the first visible upcoming item. Disabling shuffle restores the intended base order. Manual reorder while shuffled no longer destroys the base order.
- Improved playback metadata flow by allowing `AudioEngine.open_files/enqueue_files/play_next_files` to accept TrackRecord-like objects; queue/MPRIS/notifications/player surfaces receive consistent metadata.
- Added `ui/components/artwork.py`, `track_table.py`, `queue_row.py`, `track_tile.py`, and `track_shelf.py` for lightweight reusable rendering.

### Files created/modified
- Created: `services/ambient_palette.py`, `ui/components/artwork.py`, `ui/components/queue_row.py`, `ui/components/track_shelf.py`, `ui/components/track_table.py`, `ui/components/track_tile.py`, `tests/test_atmospheric_ui.py`.
- Modified: `core/theme_manager.py`, `main.py`, `services/audio_engine.py`, `services/queue_manager.py`, `ui/components/queue_panel.py`, `ui/main_window.py`, `ui/mini_player.py`, `ui/pages/base_page.py`, `ui/pages/home_page.py`, `ui/pages/now_playing_page.py`, `ui/pages/songs_page.py`, `ui/pages/albums_page.py`, `ui/pages/favorites_page.py`, `ui/pages/playlists_page.py`, `ui/pages/recently_played_page.py`, `ui/player_bar.py`, `README.md`, `DEVELOPMENT_LOG.md`.

### Verification
- Baseline before redesign: `QT_QPA_PLATFORM=offscreen ../.isai/bin/python -m unittest discover -s tests -v` — **116 tests, OK**.
- Targeted: `QT_QPA_PLATFORM=offscreen ../.isai/bin/python -m unittest tests.test_atmospheric_ui tests.test_queue tests.test_ui tests.test_now_playing_lyrics tests.test_ui_session5 -v` — **66 tests, OK**.
- Full suite: `QT_QPA_PLATFORM=offscreen ../.isai/bin/python -m unittest discover -s tests -v` — **123 tests, OK (288.401s)**.
- `../.isai/bin/python -m compileall -q .` — **OK**.
- `../.isai/bin/python -m pip check` — **No broken requirements found**.

### Known limitations
- Artwork ambience is derived from a small sampled image; it is intentionally subtle and may be neutral for low-saturation artwork.
- QSS cannot animate every property; motion is limited to opacity/geometry where Qt widgets support it and respects reduced motion.
- Very large libraries still use `QTableWidget` for song/playlist/detail tables; model/view virtualization is a future performance step.
- Live desktop manual verification (real audio device, MPRIS client behavior, Wayland/X11 compositor differences) should be performed on the target Zorin OS desktop.

## Post-Session 10 - Layout fix: maximize content area and song list height

### Root cause
- `ui/pages/base_page.py` added `outer.addStretch(1)` after the page body, so all extra vertical space was consumed below content instead of by the content itself.
- Table/list content widgets were added to `body` with default stretch 0 and only a minimum height, so they stayed short while the trailing stretch created a large empty gap above the bottom player.

### Layout changes
- `BasePage`: changed body to fill available space (`outer.addLayout(self.body, 1)`) and removed the trailing outer stretch. Page body now owns vertical expansion.
- Table/list pages: added main table/list/grid/detail containers with `stretch=1` and `QSizePolicy.Expanding` vertically; empty states also expand when visible. Hidden widgets remain layout-ignored by Qt.
- Top-aligned content pages: added trailing `self.body.addStretch(1)` in Home and Settings so sections remain naturally top-aligned inside the filled scroll content.

### Pages affected
- `Songs`, `Recently Played`, `Favorites`, `Playlists` (list/detail tables), `Albums` (grid/detail table), `Artists` (grid), `Home`, `Settings`. `Now Playing` already used a stretching canvas; `QueuePanel` already stretched its list.

### Verification
- Offscreen resize sanity check (Recently Played, 20 tracks): 1200x760 -> table 513px, 1200x900 -> 653px, 1000x650 -> 403px.
- `QT_QPA_PLATFORM=offscreen ../.isai/bin/python -m unittest discover -s tests -v` — **123 tests, OK (246.931s)**.
- `../.isai/bin/python -m compileall -q .` — **OK**.
- `../.isai/bin/python -m pip check` — **No broken requirements found**.
- `../.isai/bin/python -m pytest -q` — **not available** (`No module named pytest` in the project venv).


## Session 11 - Settings and performance optimization

### Summary
- Added centralized Session 11 Settings page with sections: Appearance, Playback, Library, Notifications and Linux Integration, Storage and Cache, and About ISAI.
- Added `core/app_settings.py` for typed settings keys/defaults/invalid-value recovery over QSettings.
- Added playback settings: default volume, resume playback position, remember playback state, default repeat, default shuffle. Volume/defaults persist; queue restore respects remember/resume settings.
- Added library folder registration in SQLite (`library_folders` table), folder add/remove UI, rescan registered folders, optional background startup scan, and library statistics.
- Added storage/cache controls: artwork cache location/size, database path/size, clear artwork cache with confirmation, clear ISAI temp files with confirmation. Cache cleanup removes only cache files and clears stale cache artwork paths; it does not delete music files or the library database.
- Preserved Linux integration controls/status: notifications, close-to-tray, tray availability, MPRIS status.

### Files created/modified
- Created: `core/app_settings.py`, `tests/test_session11_settings_perf.py`.
- Modified: `ui/pages/settings_page.py`, `ui/main_window.py`, `services/library_database.py`, `services/artwork_cache.py`, `README.md`, `DEVELOPMENT_LOG.md`.

### Performance measurements (actual, offscreen dev environment)
- Offscreen startup sanity measurement (Python import/app/window show, temp empty DB/settings):
  - `import=0.744s app=0.493s window=0.803s total=2.040s` (`/usr/bin/time -p real 2.43s, user 1.40s, sys 0.19s`)
- No speculative aggressive optimizations were applied. Existing background scanning, lazy artwork loading, bounded caches, and event-driven playback updates were preserved. Real desktop idle CPU/RAM/playback measurements should be captured on the target Zorin OS desktop with a representative library.

### Verification
- `QT_QPA_PLATFORM=offscreen ../.isai/bin/python -m unittest tests.test_session11_settings_perf -v` — **5 tests, OK**.
- `QT_QPA_PLATFORM=offscreen ../.isai/bin/python -m unittest discover -s tests -v` — **129 tests, OK (276.853s)**.
- `../.isai/bin/python -m compileall -q .` — **OK**.
- `../.isai/bin/python -m pip check` — **No broken requirements found**.
- `../.isai/bin/python -m pytest -q` — **not available** (`No module named pytest` in project venv).

### Known limitations
- Performance numbers above are from an offscreen automated environment, not a full desktop user-session measurement; capture desktop idle/playback CPU and RSS on Zorin OS for production-quality baselines.
- Cache cleanup clears extracted artwork cache files and nulls stale cache artwork paths; artwork will be re-extracted on next scan/playback as needed.
- Startup scan is optional and runs only for registered folders; it does not remove missing tracks unless existing scan/database rules do so.
