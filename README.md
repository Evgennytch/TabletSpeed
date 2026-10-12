# TabletSpeed

TabletSpeed is a Windows desktop overlay for osu! players. It measures Windows cursor motion and displays speed and distance in a transparent, configurable overlay.

**Кратко:** TabletSpeed — открытая утилита для измерения движения курсора/пера и отображения показателей поверх игры.

## Current features

- Cursor coordinates sampled off the GUI thread at 60 Hz through the Windows API.
- Direct OTD-IPC v2 source with local discovery, protocol handshake, binary state parsing, and optional physical-unit calibration.
- Current smoothed speed, average speed, peak speed, map and session distance. The cursor source is explicitly measured in screen pixels, not physical hand speed.
- Noise threshold, smoothing, optional manual cm calibration, per-metric colors, visibility toggles for each overlay value, compact labels, vertical/horizontal layout, graph, TTF/OTF fonts, font size, position, topmost and click-through settings.
- User-selected Windows sign-in startup, global Ctrl+Shift hotkeys, profile CRUD/import/export, and a mini speed graph.
- Tray controls, settings window that hides on close/minimize, persisted window position, built-in color presets, and global shortcuts: Ctrl+Shift+O overlay, +P settings, +N new map/reset map, +S session reset, +M max reset, +G graph, +L interaction lock.
- Versioned JSON settings in `%APPDATA%\TabletSpeed`, with a backup and corrupt-file preservation.
- Optional localhost-only OBS Browser Source server (start/stop from tray).
- Pure core functions for physical-area sizing and distance unit conversion.

## Known limitations

This is an initial MVP, not the full feature list in the original specification. The direct OpenTabletDriver source uses OTD-IPC v2 discovery and local sockets. Install and enable a compatible OTD IPC filter plugin first. The source is exclusive and may disable OTD's normal output while connected, so TabletSpeed shows a confirmation before connecting. osu! may stop receiving tablet motion unless another output path is configured. Follow the [OTD-IPC setup guide](https://otd-ipc.openkneeboard.com/getting-started/) and [protocol](https://otd-ipc.openkneeboard.com/protocol/).

Physical calibration requires manually entering the tablet active dimensions and its mapped screen dimensions; incorrect values produce incorrect physical units. Automated map detection, arbitrary ordering/drag-and-drop layout, and user-editable hotkey bindings are not implemented. The overlay can be moved and resized from its bottom-right corner when click-through is disabled. OBS Browser Source is a basic local page; window capture compatibility depends on Windows/OBS capture method and has not been manually verified here. This project has not been built or run on a clean Windows machine, so no such compatibility claim is made.

## Подключение планшета через OpenTabletDriver (OTD-IPC)

1. Установи и запусти [OpenTabletDriver](https://opentabletdriver.net/). Убедись, что планшет подключён и виден в OTD.
2. В OTD открой **Plugin Manager**, найди и установи **OpenKneeboard OTD-IPC**. Это именно IPC-фильтр; отдельно устанавливать OpenKneeboard не требуется.
3. Выбери свой планшет в OTD, открой **Filters**, выбери **OpenKneeboard**, включи **Enable OpenKneeboard (OTD-IPC)**, затем нажми **Save** и **Apply**. Если планшетов несколько, настрой фильтр для нужного планшета.
4. Оставь OTD запущенным. Он публикует файлы обнаружения автоматически; вручную создавать `default.txt` не нужно. Проверить их можно через Win+R, открыв `%LOCALAPPDATA%\otd-ipc\servers\v2`. В `default.txt` записан ID реализации, а файл с таким ID в подпапке `available` содержит строку `SOCKET=...`.
5. Запусти TabletSpeed, открой настройки сочетанием **Ctrl+Shift+P** и выбери источник координат **OpenTabletDriver IPC (plugin required)**. Подтверди предупреждение о прямом эксклюзивном подключении. Строка состояния должна показать имя планшета либо сообщение об ожидании движения пера.

### `cm/s` и `mm/s` в обычном режиме Windows cursor

Можно оставить **Windows cursor**, чтобы не подключаться к OTD-IPC и не отключать обычный ввод в osu!, и при этом видеть физические единицы. Для этого в настройках TabletSpeed задай калибровку:

- **Active tablet width/height** — ширина и высота активной области планшета в сантиметрах. Укажи рабочую область, которую OTD отображает на экран, а не обязательно габариты всего планшета.
- **Mapped screen width/height** — ширина и высота области экрана, соответствующей этой рабочей области, в пикселях. Если отображение идёт на весь монитор, укажи его разрешение, например `1920 × 1080`.
- **Calibrated speed unit** — выбери `cm/s` или `mm/s`. Единицу расстояния можно выбрать отдельно в **Calibrated distance unit**.

Нужны все четыре ненулевых значения ширины и высоты. Одного выбора `cm/s` недостаточно: пока калибровка не заполнена, скорость и расстояние остаются в `px/s` и `px`. При появлении подтверждения изменения калибровки выбери **Yes** — приложение сбросит текущие измерения и применит новые значения. Поля **Tablet physical diagonal** и **Whole-device aspect ratio** служат для справки и сами по себе пересчёт не включают.

**Важно:** OTD-IPC предоставляет TabletSpeed эксклюзивный доступ к данным пера и может отключить обычный режим вывода OpenTabletDriver. Из-за этого osu! может перестать получать ввод. Если это произошло, вернись к источнику **Windows cursor** в настройках TabletSpeed, либо настрой отдельный совместимый путь вывода пера. Не запускай одновременно другое приложение, которое уже использует OTD-IPC: подключение может быть только одно.

Если источник сообщает ошибку, сначала проверь, что OTD запущен, фильтр включён и применён, и что `%LOCALAPPDATA%\otd-ipc\servers\v2\default.txt` существует. Если ошибка содержит `Could not connect to OTD-IPC socket`, перезапусти OTD и проверь, что путь `SOCKET=` из файла `available` существует. После изменения настроек фильтра снова нажми **Save** и **Apply**.

## Requirements and run from source

Windows 10/11 x64, Python 3.11+, and pip. In PowerShell from the project directory:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Dependencies: PySide6-Essentials (LGPLv3/GPLv3/commercial Qt licensing options; see Qt terms), aiohttp (Apache-2.0), pytest (MIT; development), PyInstaller (GPL-2.0-or-later with bootloader exception; build only). No third-party fonts or images are bundled.

## OBS Browser Source

Use the settings or tray menu to start/stop the OBS source and copy its configured URL, then paste it into OBS Browser Source (default `http://127.0.0.1:8765/`). The listener binds only to localhost and starts only when requested. The display updates over a local WebSocket. Stop it from the same tray menu or exit the app.

## Build a Windows EXE

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
.\build_windows.bat
```

The script creates `dist\TabletSpeed\TabletSpeed.exe` as a windowed one-folder build. It uses `.venv` when that environment has pytest available, otherwise it uses the active Python environment. Test the resulting executable on the target Windows installation before distribution. A bundled offscreen lifecycle check is available with `dist\TabletSpeed\TabletSpeed.exe --smoke-test`; preserve the adjacent `_internal` directory when running the app.

## Tests

Run `python -m pytest`. Tests cover measurement math, settings recovery/version handling, profile import/export, OTD frame parsing, and local OBS page startup/shutdown. Qt controller startup/shutdown was also exercised with the offscreen platform. Global hotkey conflicts, Windows tray behavior, tablet-driver connection and actual game click-through still require a normal desktop session with the relevant hardware/software.

## Roadmap

1. Windows manual checks for tray, overlay, click-through and global hotkey conflicts.
2. Hardware validation with supported OTD-IPC filter plugins and tablet calibration.
3. Drag-and-drop ordering and user-editable global shortcuts.
4. OBS window-capture compatibility checks and Browser Source configuration UI.
5. Clean-machine EXE validation and signed release packaging.
