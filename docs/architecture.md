> **Not (Ekim 2026):** Bu belge yeniden yapılanmanın başındaki durumu anlatır ve tarihsel kayıttır. Burada sözü edilen kaynak koddaki Gemini anahtarı kaldırıldı; anahtarlar artık sadece `.env`'de durur. Güncel mimari ve kullanım için [beyin.md](beyin.md) ve [README](../README.md).

# IRLE Architecture Review and Rebuild Plan

## Current Snapshot

IRLE is currently a Windows-focused assistant made of:

- Desktop Python app entrypoint: `main.py`
- Event bus: `core/event_bus.py`
- Voice input: `modules/ses_modulu.py`
- Decision layer: `modules/llm_modulu.py`
- Actions: `modules/aksiyon/*`
- Memory: `modules/bellek_modulu.py`
- TTS: `modules/tts_modulu.py`
- Vision/gesture control: `modules/vision_modulu.py`
- Tkinter GUI: `modules/gui_modulu.py`
- Phone controller server: `modules/telefon_kontrolcu.py`
- Separate PWA server: `kontrolcu_app.py`
- Flutter controller app: `kontrolcu_mobile/`

The current code compiles, but the architecture has grown organically. The next version should keep the working ideas, but rebuild the boundaries.

## Biggest Problems

1. `modules/llm_modulu.py` has too many responsibilities.
   It decides intent, calls Gemini, contains the offline rule engine, manipulates OS state, controls media, manages notes, starts timers, opens web pages, checks camera, and runs system commands.

2. Configuration is unsafe and too global.
   `config.py` contains a hardcoded Gemini API key and runtime modules read globals directly. Runtime state such as calibration also edits `config.py` directly.

3. Event names are stringly typed.
   Events like `tts_konuş`, `uygulama_ac`, and `el_hareketi_algilandi` are raw strings spread across modules. Typos will only fail at runtime.

4. Thread lifecycle is fragile.
   Most modules create daemon threads, but there is no shared lifecycle contract, cancellation token, health check, or join policy.

5. OS side effects are mixed into business logic.
   `pyautogui`, `subprocess`, `webbrowser`, `cv2`, `screen_brightness_control`, and WMI calls appear in high-level modules.

6. UI and server assets are inline.
   `telefon_kontrolcu.py` and `kontrolcu_app.py` contain large embedded HTML/CSS/JS blocks. This makes testing and iteration harder.

7. Generated/build artifacts are in the project tree.
   `__pycache__`, Flutter `build/`, and the release APK are present beside source files. They should be ignored or moved to release artifacts.

8. Encoding is inconsistent.
   Many comments/strings appear mojibaked in terminal output. The project should standardize on UTF-8 and avoid path-sensitive model locations.

## Target Architecture

Use a small clean architecture layout:

```text
src/irle/
  app/
    bootstrap.py
    lifecycle.py
    settings.py
  domain/
    commands.py
    events.py
    intents.py
    results.py
  ports/
    speech.py
    intent.py
    tts.py
    memory.py
    actions.py
    vision.py
    controller.py
  services/
    intent_service.py
    command_router.py
    conversation_service.py
  adapters/
    speech/
    intent/
    tts/
    memory/
    windows/
    vision/
    controller_server/
    gui/
  infra/
    event_bus.py
    logging.py
    paths.py
  tests/
```

## Layer Rules

- `domain/` contains pure dataclasses/enums and no IO.
- `services/` contains orchestration and business flow.
- `ports/` defines interfaces/protocols.
- `adapters/` talks to real libraries and the OS.
- `app/` wires everything together.
- No adapter imports another adapter directly unless it is an explicit composition adapter.
- No module reads global `config.py` directly. All settings flow through `Settings`.

## Proposed Event and Command Model

Replace free-form event strings with typed names and payloads:

```python
class EventName(StrEnum):
    SPEECH_RECOGNIZED = "speech.recognized"
    INTENT_RESOLVED = "intent.resolved"
    COMMAND_REQUESTED = "command.requested"
    COMMAND_COMPLETED = "command.completed"
    TTS_REQUESTED = "tts.requested"
    TTS_COMPLETED = "tts.completed"
    NOTIFICATION = "notification"
```

Commands should be explicit:

- `OpenApplication(name: str)`
- `Speak(text: str)`
- `SetVolume(level: int | None, delta: int | None)`
- `SetBrightness(level: int | None, delta: int | None)`
- `MouseMove(dx: float, dy: float)`
- `MouseClick(button: MouseButton)`
- `CreateNote(text: str)`
- `SearchWeb(query: str)`
- `ShutdownComputer(delay_seconds: int)`

The intent resolver/rule engine should only produce commands. It should not execute them.

## Module Boundaries

### Speech

Responsible for microphone capture and speech-to-text only.

Outputs:

- `SpeechRecognized(text, confidence=None, source="microphone")`

### Intent

Responsible for turning text into one or more commands.

Implementations:

- `RuleBasedIntentResolver`
- `LocalModelIntentResolver` if a local/offline model is added later
- `FallbackIntentResolver`

External AI APIs are intentionally out of scope for the rebuild. The assistant should work offline-first, without Gemini/OpenAI/cloud LLM dependencies in the core runtime.

### Command Router

Responsible for dispatching typed commands to action handlers.

### Windows Actions

Responsible for actual OS integration:

- app launching
- media keys
- volume
- brightness
- screenshot
- window control
- process control
- file operations
- clipboard

### Memory

Responsible for conversation history and notes. It should expose repositories:

- `ConversationRepository`
- `NoteRepository`

### Controller Server

Responsible for Socket.IO and HTTP only. It should translate controller messages into typed commands. HTML/static assets should live outside Python source.

### Vision

Responsible for camera and gesture detection only. It should publish pointer/gesture commands, not directly control the mouse.

### GUI

Responsible for display and user interactions only. It should not own system logic.

## Settings

Move settings to:

- `.env` for secrets and local overrides
- `settings.toml` or `config/default.toml` for non-secret defaults
- `data/runtime_state.json` for calibration values and mutable runtime settings

Required first fix:

- Remove hardcoded Gemini API key from source.
- Remove external AI API settings from the active runtime path.

## Suggested First Milestones

### Milestone 1: Safety and Structure

- Add `pyproject.toml`.
- Add `.gitignore`.
- Add `src/irle` package.
- Add typed settings loader.
- Remove external AI API usage and remove the hardcoded Gemini API key from source.
- Add typed `EventBus` and event constants.
- Keep old modules running through compatibility wrappers.

### Milestone 2: Extract Intent Layer

- Split `RuleEngine` out of `llm_modulu.py`.
- Remove Gemini client code from the runtime path.
- Make the rule/local intent resolver return typed commands.
- Add unit tests for Turkish command parsing.

### Milestone 3: Extract Action Handlers

- Move OS actions from `llm_modulu.py` into dedicated handlers.
- Remove direct `pyautogui`, `subprocess`, `cv2`, and `webbrowser` calls from intent code.
- Add dry-run mode for tests.

### Milestone 4: Controller Cleanup

- Extract Socket.IO events into a controller adapter.
- Move HTML/CSS/JS into templates/static files.
- Keep Flutter event names compatible through a versioned protocol.

### Milestone 5: Vision and GUI Cleanup

- Move calibration persistence out of `config.py`.
- Route gestures through command/event model.
- Keep Tkinter as an adapter or replace it later without touching core logic.

## Recommended Immediate File Moves

Do not rewrite everything at once. First create the new package and migrate by feature:

```text
modules/llm_modulu.py
  -> src/irle/services/intent_service.py
  -> src/irle/adapters/intent/rule_engine.py
  -> optional later: src/irle/adapters/intent/local_model.py

modules/aksiyon/*
  -> src/irle/adapters/windows/actions.py
  -> src/irle/adapters/windows/app_catalog.py
  -> src/irle/adapters/windows/mouse.py

modules/telefon_kontrolcu.py
  -> src/irle/adapters/controller_server/server.py
  -> src/irle/adapters/controller_server/protocol.py
  -> src/irle/adapters/controller_server/templates/
  -> src/irle/adapters/controller_server/static/
```

## Test Strategy

Start with tests that do not touch hardware:

- Rule engine text-to-command tests
- Event bus publish/subscribe tests
- Settings loader tests
- Memory repository tests using temp files
- Controller protocol parsing tests
- Command router dry-run tests

Hardware-facing adapters should be tested with fakes first, then manual smoke scripts.

## Decision

The rebuild should be evolutionary, not a big-bang deletion. Keep the current app runnable while carving out the new core. Once the typed command pipeline is stable, old modules can be replaced one by one.
