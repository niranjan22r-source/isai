# ISAI — Installation and Setup Guide

This guide explains how to download, install, configure, and run ISAI from its source code on a Linux desktop.

> **Platform note:** ISAI is a Linux desktop application built with Python and PySide6/Qt. These instructions target Ubuntu, Zorin OS, Linux Mint, and other Debian/Ubuntu-based distributions. Other distributions may need equivalent package-manager commands.

## 1. What you need

Before starting, make sure your system has:

- A supported Linux desktop environment.
- Python 3 and `venv` support.
- Git.
- An internet connection for downloading the source and Python dependencies.
- Audio output configured and working.

The exact Python package dependencies are listed in `requirements.txt`. Use that file rather than installing packages one by one.

## 2. Install system prerequisites

Open a terminal and run:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

Check that Python and Git are available:

```bash
python3 --version
git --version
```

If your distribution separates the virtual-environment package from the main Python package, install the matching `python3-venv` package for your Python version.

## 3. Download the project

Clone the ISAI repository:

```bash
git clone <ISAI_REPOSITORY_URL>
```

Move into the application directory. In the current project layout, the application source is inside the `isai` directory:

```bash
cd <REPOSITORY_FOLDER>/isai
```

You should see files and folders similar to:

```text
isai/
├── assets/
├── core/
├── data/
├── packaging/
├── services/
├── tests/
├── ui/
├── main.py
├── launch.sh
├── requirements.txt
├── README.md
└── isai.desktop
```

The exact contents may change as the project develops.

## 4. Create a virtual environment

A virtual environment keeps ISAI's Python packages separate from your system Python installation.

From inside the `isai` application directory, run:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

After activation, your terminal prompt should show `(.venv)` or a similar environment name.

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

## 5. Install Python dependencies

Install the packages declared by the project:

```bash
pip install -r requirements.txt
```

Wait for the installation to finish. If installation fails, read the first error carefully and check that your Python version is compatible with the packages pinned in `requirements.txt`.

Do not use `sudo pip install` inside the virtual environment.

## 6. Run ISAI

### Option A — Use the launch script

If the repository's launch script is executable and configured for your environment:

```bash
chmod +x launch.sh
./launch.sh
```

### Option B — Start the application directly

With the virtual environment activated, run:

```bash
python main.py
```

The ISAI desktop window should open.

If the application does not start, see the troubleshooting section below and include the full terminal error when reporting a bug.

## 7. Add your music

1. Open ISAI.
2. Use the music-library or folder-selection option in the application.
3. Select a folder containing audio files.
4. Allow the library scanner to process the files.
5. Select a track and test playback.

ISAI does not provide music files. Use audio files that you own or are legally allowed to access.

## 8. User data and library database

ISAI may create local application data such as a music-library database, preferences, artwork cache, or other runtime files.

- Keep your personal music files in your own music folders.
- Do not commit personal music, private library databases, caches, or logs to the public Git repository.
- If you uninstall or reset the application, back up any ISAI user data you want to keep before deleting it.

The exact user-data location can vary by application version and configuration. Check the application's documentation or settings before manually removing data.

## 9. Troubleshooting

### `python3: command not found`

Install Python 3 using your distribution's package manager. On Ubuntu-based systems:

```bash
sudo apt update
sudo apt install python3
```

### `No module named ...`

Activate the virtual environment and reinstall the project dependencies:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

Make sure you run the application using the same Python environment where the dependencies were installed.

### `No such file or directory: requirements.txt`

Make sure you are inside the application directory that contains `main.py` and `requirements.txt`:

```bash
pwd
ls
```

### The launch script is not executable

Run:

```bash
chmod +x launch.sh
./launch.sh
```

### The application opens but audio does not play

- Check that your system audio works in another application.
- Check the selected output device and system volume.
- Try another supported audio file.
- Restart ISAI after changing audio-device settings.
- If the problem continues, report the terminal output and the audio format involved.

### Qt or PySide6 platform-plugin error

- Confirm that the virtual environment is active.
- Reinstall dependencies from `requirements.txt`.
- Do not copy random Qt plugin folders into the project or set arbitrary `QT_PLUGIN_PATH` values; these can cause conflicting Qt installations.
- Include the complete error message and your Linux distribution/version in a bug report.

## 10. Updating ISAI

If you installed the project by cloning the Git repository:

```bash
cd <REPOSITORY_FOLDER>
git pull
cd isai
source .venv/bin/activate
pip install -r requirements.txt
```

Then launch the application again:

```bash
./launch.sh
```

If you have local code changes, commit or back them up before pulling updates.

## 11. Development and testing

The repository includes a `tests/` directory. To run the project's tests, first activate the virtual environment and install the project requirements.

If the project declares `pytest` as a dependency, run:

```bash
pytest
```

If `pytest` is not installed or the project uses a different test runner, follow the test instructions in the repository's development documentation. Do not install extra test tools unless they are listed or required by the project.

## 12. Build packages

The repository contains packaging resources and build scripts under `packaging/`. These are intended for creating distributable Linux packages.

For the available packaging options and their prerequisites, inspect:

```text
packaging/scripts/
```

Use the relevant build script's own help text or documentation before building. Generated output directories such as `build/`, `dist/`, and `build-artifacts/` are build products; they are not required for a normal source installation.

## 13. Reporting a problem

When reporting an issue, include:

- Your Linux distribution and version.
- Output of `python3 --version`.
- The steps you followed.
- The complete terminal error or traceback.
- Whether the issue occurs during installation, startup, library scanning, or playback.

Do not attach private music files, passwords, personal databases, or other sensitive information.

---

## Quick start

For users who already have Git and Python 3 installed:

```bash
git clone <ISAI_REPOSITORY_URL>
cd <REPOSITORY_FOLDER>/isai
sudo apt update
sudo apt install -y python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

Replace `<ISAI_REPOSITORY_URL>` with the actual public GitHub clone URL and `<REPOSITORY_FOLDER>` with the directory created by `git clone`.
