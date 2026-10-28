# Prompt for Claude Sonnet 4.6

You are a senior Python architect and refactoring agent. You are working on the IRLE project, a Windows-focused Turkish offline assistant with voice input, TTS, GUI, vision/gesture control, phone controller, and OS automation.

Your task is to refactor the project toward Clean Architecture with a lightweight CQRS design while keeping the current application runnable during migration.

## Project Context

Current important files:

- `main.py`: application bootstrap
- `config.py`: global configuration, currently contains a hardcoded Gemini API key
- `core/event_bus.py`: current string-based pub/sub bus
- `modules/ses_modulu.py`: speech input
- `modules/llm_modulu.py`: currently too large; contains Gemini, rule engine, OS commands, notes, timers, media, web, etc.
- `modules/aksiyon/*`: app launching and mouse actions
- `modules/bellek_modulu.py`: JSON conversation memory
- `modules/tts_modulu.py`: pyttsx3 TTS
- `modules/vision_modulu.py`: OpenCV/MediaPipe gesture detection
- `modules/gui_modulu.py`: Tkinter GUI
- `modules/telefon_kontrolcu.py`: Flask/Socket.IO phone controller with inline HTML/CSS/JS
- `kontrolcu_app.py`: standalone PWA controller server
- `kontrolcu_mobile/`: Flutter mobile controller app
- `docs/architecture.md`: desired architecture plan

## Non-Negotiable Decisions

1. Remove external AI API usage from the runtime path.
2. Remove the hardcoded Gemini API key from source.
3. Do not add OpenAI, Gemini, Anthropic, or other cloud LLM dependencies.
4. The assistant must be offline-first.
5. Use Clean Architecture.
6. Use lightweight CQRS: typed Commands for state-changing actions, typed Queries for reads, typed Events for notifications.
7. Do not do a big-bang rewrite. Keep the current app runnable while migrating feature by feature.
8. Keep Turkish command support.
9. Prefer small, testable Python modules over large god files.
10. Avoid breaking the Flutter controller Socket.IO protocol unless you provide a compatibility layer.

## Target Architecture

Create or evolve toward:

```text
src/irle/
  app/
    bootstrap.py
    lifecycle.py
    settings.py
  domain/
    commands.py
    queries.py
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
    command_bus.py
    query_bus.py
    conversation_service.py
  adapters/
    intent/
      rule_engine.py
    speech/
    tts/
    memory/
    windows/
      app_catalog.py
      actions.py
      mouse.py
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

- `domain/` must be pure Python dataclasses/enums and contain no IO.
- `services/` orchestrates use cases.
- `ports/` defines protocols/interfaces.
- `adapters/` talks to libraries, OS, files, camera, Flask, Tkinter, pyautogui, pyttsx3, etc.
- `app/` wires dependencies together.
- No adapter should import another adapter directly unless it is an explicit composition adapter.
- No core/service/domain code should import `pyautogui`, `cv2`, `flask`, `subprocess`, `webbrowser`, `pyttsx3`, `speech_recognition`, or MediaPipe.
- No module should read global `config.py` directly after migration. Use a typed `Settings` object.

## CQRS Model

Define explicit command/query/event models.

Examples of Commands:

- `OpenApplication(name: str)`
- `Speak(text: str)`
- `SetVolume(level: int | None = None, delta: int | None = None)`
- `SetBrightness(level: int | None = None, delta: int | None = None)`
- `MouseMove(dx: float, dy: float)`
- `MouseClick(button: str)`
- `CreateNote(text: str)`
- `SearchWeb(query: str)`
- `ShutdownComputer(delay_seconds: int)`

Examples of Queries:

- `GetBatteryStatus`
- `ListNotes`
- `GetAppCatalog`
- `GetConversationHistory`
- `GetControllerStatus`

Examples of Events:

- `SpeechRecognized`
- `IntentResolved`
- `CommandRequested`
- `CommandCompleted`
- `CommandFailed`
- `TtsRequested`
- `TtsCompleted`
- `Notification`
- `ControllerConnected`

## First Implementation Milestone

Implement the first safe migration step only:

1. Add `pyproject.toml` with project metadata and test tooling if missing.
2. Add or update `.gitignore` to exclude `__pycache__/`, `.pytest_cache/`, virtualenvs, Flutter build output, and generated release artifacts.
3. Create `src/irle/` package skeleton.
4. Add typed domain models:
   - `src/irle/domain/commands.py`
   - `src/irle/domain/queries.py`
   - `src/irle/domain/events.py`
5. Add `src/irle/app/settings.py`.
   - Load secrets from environment.
   - Do not require an AI API key.
   - Do not include any hardcoded API key.
6. Add `src/irle/infra/event_bus.py`.
   - Support typed event names.
   - Preserve simple subscribe/publish semantics.
   - Avoid starting unbounded threads per handler if you can implement a safer executor.
7. Extract the offline rule engine from `modules/llm_modulu.py` into:
   - `src/irle/adapters/intent/rule_engine.py`
   - It should return typed command objects, not execute OS operations.
8. Update the old `modules/llm_modulu.py` minimally so it can use the new rule engine in offline mode.
   - Remove Gemini client initialization from the active path.
   - Remove hardcoded API key dependency.
   - Keep old event names working for now through compatibility translation.
9. Add focused tests for:
   - Turkish text to command parsing
   - settings loader
   - event bus
10. Run compile/tests and fix failures.

## Migration Constraints

- Do not delete working modules yet.
- Do not rewrite GUI, vision, phone server, or Flutter app in the first milestone.
- Keep changes scoped and reviewable.
- Preserve current behavior where practical.
- If behavior must change, document it.
- Use UTF-8.
- Do not store secrets in source.

## Expected Output

When finished, provide:

1. Summary of files changed.
2. What behavior is preserved.
3. What cloud AI/API code was removed or disabled.
4. Test/compile commands run and their results.
5. Next recommended milestone.

## Architectural Intent

The end goal is:

```text
Input adapters
Speech / GUI / Phone / Vision
        |
        v
Intent resolver
Offline Turkish rule parser, optional local model later
        |
        v
Command bus
Typed command dispatch
        |
        v
Command handlers
Windows actions, memory, TTS, controller, etc.
        |
        v
Events / Notifications
GUI, logs, TTS, state updates
```

Build the foundation carefully. Prefer correctness and clear boundaries over aggressive rewrites.
