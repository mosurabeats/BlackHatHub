# Tessera

An original desktop music workstation built around two connected ways of working:

- **Session view:** a grid of looping clips you launch live.
- **Arrangement view:** a timeline you export as a finished track.

Tessera is written in C++ with [JUCE](https://juce.com). It runs natively on macOS (universal Apple Silicon + Intel) and Linux; Windows builds should work with the same CMake project but are untested.

> Tessera is its own product with its own name, design and code. It is inspired by the clip-launching workflow common to modern DAWs, but it does not copy any other application's branding, artwork or interface.

## What works today (v0.1)

| Area | Features |
|---|---|
| **Session view** | Clip grid (tracks × scenes); launching quantized to 1, 2 or 4 bars, or immediate; scene launch; per-track stop; Stop All; looping clips with progress; queued/playing indicators; record 4 bars of MIDI into an empty slot (the new clip starts playing in time); create, rename, duplicate and delete clips; copy a clip to the arrangement |
| **Arrangement view** | Timeline with zoom and scroll; drag clips to move them (across tracks of the same kind); drag the right edge to resize (loops or trims); loop region (shift-drag the ruler); playhead follow; double-click to create a clip; drop audio files onto lanes; mute/solo/arm per lane |
| **MIDI** | Piano roll: add, move and resize notes, set velocity (shift-drag), delete, grid 1/4–1/32, quantize, double the loop, audition from the keyboard strip; record from a MIDI controller or the computer keyboard (A–K, Z/X for octave); arrangement MIDI recording |
| **Instruments** | **Poly Synth:** 12 voices, 2 oscillators, filter with envelope, ADSR. **Drum Sampler:** 16 pads with a built-in synthesized kit, drop your own samples on pads, tune, decay, choke between closed and open hi-hat |
| **Audio** | Import WAV/AIFF/FLAC/Ogg/MP3 by dragging from the built-in browser or from Finder; audio clips in slots and on the timeline; warp by re-pitching to follow the project tempo, or play at native speed; clip gain; waveform view; record audio from your interface input onto an armed audio track |
| **Mixer & effects** | Per-track volume, pan, mute, solo, arm and meters; master volume and meter. Insert effects: 3-band EQ, compressor, tempo-synced delay, reverb, multimode filter. Effects can be added, bypassed, reordered and removed |
| **Project** | Save and open `.tessera` projects (JSON; saves are atomic, so a crash can't corrupt them); unlimited undo/redo (up to 200 steps); metronome; tempo; export the arrangement to a 24-bit WAV with an effects tail; demo project; audio/MIDI device settings |

Default shortcuts are listed under **Help → Keyboard & Workflow Help**.

## Install on your Mac

**Option A — download the build from GitHub Actions (no tools needed)**

1. In the repository, open **Actions → "Tessera (desktop DAW)"**, select the latest successful run, and download the **Tessera-macOS** artifact.
2. Unzip it (it contains `Tessera-macOS.zip` — unzip that too) and drag **Tessera.app** into **Applications**.
3. The app is not notarized by Apple, so the first launch needs one extra step. Right-click **Tessera.app → Open → Open**. If macOS says it is "damaged", run this once in Terminal:
   `xattr -dr com.apple.quarantine /Applications/Tessera.app`
4. Choose your audio interface under **File → Audio / MIDI Settings**. The first time you record audio, macOS asks for microphone access.

**Option B — build it yourself**

```bash
xcode-select --install        # once
brew install cmake            # once
cd tessera && ./scripts/build-mac.sh
open build/Tessera_artefacts/Release/Tessera.app
```

The first build downloads JUCE 8.0.4 (about 100 MB) and takes a few minutes.

## Build & test (any platform)

```bash
cmake -S tessera -B tessera/build -DCMAKE_BUILD_TYPE=Release
cmake --build tessera/build -j
tessera/build/TesseraTests_artefacts/Release/TesseraTests   # headless engine/model tests
tessera/build/Tessera_artefacts/Release/Tessera --demo      # launch with the demo project
```

Linux needs `libasound2-dev libx11-dev libxrandr-dev libxinerama-dev libxcursor-dev libfreetype-dev libgl1-mesa-dev`.

## Architecture

```
Source/
  Model/      Project (value type, JSON), Params (shared parameter definitions),
              ProjectController (edits, undo/redo, save/load, snapshot publishing)
  Engine/     AudioEngine (real-time renderer), Instruments (PolySynth, DrumSampler),
              Effects, AudioFileCache, Exporter (offline render), ParamExchange
  UI/         MainComponent, TransportBar, SessionView, ArrangementView,
              ClipEditor, DeviceView, BrowserView, Theme
Tests/        Headless unit tests (render audio and assert on it)
```

**Real-time safety**

- The UI never touches engine state directly. Each edit produces an immutable project snapshot.
- The audio thread picks up each new snapshot with a try-lock and never frees memory; old state is released on the UI thread.
- Commands (launch, stop, notes) travel through a lock-free FIFO.
- Parameters reach DSP through `ParamExchange`, a try-lock handoff.
- Recorded MIDI comes back through a second lock-free FIFO.
- Audio recording uses JUCE's `ThreadedWriter`, with an 8-second buffer.

Every musical position is measured in beats. Clip launches, stops and loop wrap-arounds happen on the exact sample.

## Licensing note

JUCE 8 is dual-licensed: **AGPLv3**, or a commercial JUCE licence. The commercial licence includes a free "Starter" tier for individuals and companies under a revenue threshold; check the current terms at juce.com. Before you distribute Tessera commercially or closed-source, get the right JUCE licence.

## Known limitations

These are the gaps against a mature commercial DAW:

- **Warping:** warping re-pitches the audio (speed and pitch change together). There's no time-stretching that keeps the pitch yet. A path would be the Rubber Band library, which is GPL or commercial.
- **Audio recording:** recording goes to the arrangement only, from inputs 1–2, for the first armed audio track. Session audio-slot recording isn't implemented.
- **Plug-ins:** there's no VST3/AU hosting yet. JUCE's `AudioPluginFormatManager` is the natural next step.
- **Mixing:** there's no automation, sends/returns or group tracks, and no MIDI export or import.
- **Export scope:** export renders the arrangement only. Session clips must be copied to the timeline first.
- **Distribution:** the Mac app is ad-hoc signed, not notarized. Notarization needs an Apple Developer account ($99/yr).
- **Testing:** the interface was tested by building it and by launch screenshots on Linux (and on the macOS CI runner). It hasn't had hands-on testing with a real audio interface or controller.
