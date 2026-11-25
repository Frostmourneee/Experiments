# whisper-local-asr

Local English transcription with `faster-whisper`, plus a warm background
daemon used by Neovim/Neovide and a system-wide clipboard dictation command.

The model configuration is shared by the one-shot CLI and daemon:

- `large-v3`
- CUDA with `int8_float16`
- English transcription, beam size 5, VAD, no timestamps
- a short software-engineering `initial_prompt`
- no hotwords

## One-shot CLI

```bash
uv run python whisper_tool.py /path/to/audio.wav
```

## Background daemon

The user service loads and warms the model once, then listens on
`$XDG_RUNTIME_DIR/whisper-local-asr.sock`. It intentionally supports only one
sequential cycle:

```text
idle -> recording -> transcribing -> idle
```

There is no transcription queue and no concurrent ASR. Recordings are captured
as 16 kHz mono PCM WAV with FFmpeg, stored temporarily under
`~/.cache/whisper-local-asr/recordings`, and removed after success, failure, or
cancellation.

Manual service controls:

```bash
systemctl --user start whisper-local-asr.service
systemctl --user stop whisper-local-asr.service
journalctl --user -u whisper-local-asr.service
```

The Neovide launcher starts the service idempotently before opening each new
Neovide instance. The daemon sends one desktop notification after a successful
load and warm-up, or one brief error notification if startup fails.

The service is intentionally not enabled at login. It starts when Neovide is
opened through the launcher or when global clipboard dictation is first used.

## Neovim workflow

In Normal, Insert, or Terminal mode:

1. Press `Alt-V` to focus the current Codex buffer and begin recording.
2. Press `Alt-V` again to stop and transcribe.
3. The transcript is appended as a bracketed paste without submitting it.
4. Neovim enters Terminal mode so the prompt can be edited and submitted
   manually.

The Codex title shows a blinking red square while recording and a blinking
yellow square while transcribing. If there is no Codex buffer, the mapping does
nothing.

## System-wide clipboard workflow

The installed client entry point also provides a desktop toggle:

```bash
whisper-local-asr-client toggle-clipboard
```

The first invocation starts the user service when necessary, waits for model
warm-up, begins recording, and stores the recording ID under
`$XDG_RUNTIME_DIR`. The second invocation stops and transcribes, removes that
runtime state, and copies non-empty text through `xclip` on X11 or `wl-copy` on
Wayland. A nonblocking runtime lock ignores additional shortcut presses while
transcription is already in progress.

The configured GNOME shortcuts are:

- `Ctrl-Alt-N`: start the service and open Neovide.
- `Ctrl-Alt-V`: toggle system-wide clipboard dictation.
