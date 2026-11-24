#pragma once
#include "AudioEngine.h"

namespace tessera
{

struct ExportOptions
{
    double sampleRate = 48000.0;
    int bitDepth = 24;
    double startBeat = 0.0;
    double endBeat = -1.0;        // < 0: end of arrangement
    double tailSeconds = 2.0;     // reverb/delay tail after the last beat
};

// Offline render of the ARRANGEMENT (session clips are not included) to a WAV file.
// Runs a private AudioEngine faster than real time; safe to call on any non-audio thread.
// `progress` (0..1) may be polled from another thread; set `cancel` to abort.
bool exportArrangement (std::shared_ptr<const Project> project, const juce::File& out, const ExportOptions& opts,
                        juce::String& error, std::atomic<double>* progress = nullptr, std::atomic<bool>* cancel = nullptr);

} // namespace tessera
