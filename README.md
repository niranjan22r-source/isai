# ISAI

**A desktop music player for Linux, built with Python and PySide6.**

ISAI is a native-style Linux desktop music player project focused on a clean, modern listening experience. It brings your local music library, playback controls, playlists, favourites, queue management, and audio tools together in one desktop application.

> **Project status:** Under active development. Features, installation steps, and packaging may change between versions.

## Features

The current codebase includes components for:

- **Local music library** — scan and manage music from folders on your computer.
- **Playback** — audio playback engine and playback controls.
- **Playlists and favourites** — organise tracks and keep favourites close.
- **Queue management** — manage the tracks lined up for playback.
- **Metadata and artwork** — read track metadata and manage cached artwork.
- **Lyrics** — lyrics service and lyrics-related UI components.
- **Equalizer** — equalizer controls and digital signal-processing components.
- **Desktop integration** — MPRIS media controls, system tray, and desktop notifications.
- **Interface customisation** — theme management and interface components.

Some capabilities may depend on the current application version and system configuration.

## Technology

- **Language:** Python
- **Desktop UI:** PySide6 / Qt
- **Local data:** SQLite-backed library database
- **Platform:** Linux

## Project structure

The main application directory is organised into these areas:

```text
isai/
├── assets/          # Application icons and other visual resources
├── core/            # Application settings, resources, and theme management
├── data/            # Application data/cache area
├── packaging/       # Linux packaging resources and build scripts
├── services/        # Playback, library, metadata, lyrics, queue, and audio services
├── tests/           # Automated tests
├── ui/              # Main window, pages, components, and player interface
├── main.py          # Application entry point
├── launch.sh        # Launch helper
├── requirements.txt # Python dependencies
├── isai.desktop     # Desktop launcher entry
└── README.md
```

Generated folders such as `build/`, `dist/`, and `build-artifacts/` are build outputs and are not needed to run the application from source.

## Installation

### Requirements

- A Linux desktop system.
- Python 3.
- Git.
- `python3-venv` and `python3-pip`.
- Working system audio.

The Python dependencies are declared in `requirements.txt`.

### 1. Install system packages

On Ubuntu, Zorin OS, Linux Mint, and other Debian/Ubuntu-based distributions:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

### 2. Clone the repository

Replace the URL below with the actual URL of this GitHub repository:

```bash
git clone https://github.com/niranjan22r-source/isai.git
cd isai
```

### 3. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Python dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Run ISAI

```bash
python main.py
```

Alternatively, if the launch script is executable and configured for your system:

```bash
chmod +x launch.sh
./launch.sh
```

For a more detailed, step-by-step guide, see **[ISAI Installation Guide](ISAI_INSTALLATION.md)**.

## Add your music

1. Launch ISAI.
2. Open the library or folder-selection option.
3. Choose a folder containing your audio files.
4. Allow ISAI to scan the folder.
5. Select a track and start playback.

ISAI does not include music files. Use music that you own or are legally permitted to access.

## Development

To work on the source code:

```bash
git clone https://github.com/niranjan22r-source/isai.git
cd isai

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt

python main.py
```

### Running tests

The repository contains a `tests/` directory. If `pytest` is included in the project's dependencies, run:

```bash
pytest
```

Check the test configuration and development notes if a different test runner is used.

## Packaging

Packaging scripts and desktop resources are located in:

```text
packaging/
├── resources/
└── scripts/
```

The scripts currently include helpers for building AppImage and Debian packages, as well as a PyInstaller build and cleanup workflow. Review each script before running it and install any build prerequisites it requires.

Build outputs should not be committed to the source repository unless they are intentionally being published as release assets.

## Troubleshooting

- **Missing Python module:** activate `.venv` and run `pip install -r requirements.txt` again.
- **Application does not start:** run `python main.py` from the application directory and inspect the complete terminal error.
- **Audio does not play:** verify system audio output, try another audio file, and check the selected output device.
- **Qt platform plugin error:** make sure the virtual environment is active and avoid mixing system Qt libraries with the packages installed in the virtual environment.

When reporting a problem, include your Linux distribution/version, Python version, steps to reproduce, and the full terminal traceback. Do not include private music files, personal databases, or sensitive information.

## Contributing

Contributions, bug reports, and suggestions are welcome.

Before submitting a change:

1. Keep changes focused and explain their purpose.
2. Test the affected functionality.
3. Avoid committing virtual environments, generated build files, caches, logs, personal databases, or music files.
4. Describe any new dependencies or system requirements.

## License

No license has been specified in this repository yet. Until a license is added, the source code is not automatically granted an open-source reuse license. Add a `LICENSE` file before inviting others to redistribute or reuse the project.

---

Made with Python and PySide6 for Linux.
