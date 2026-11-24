#pragma once
#include "Engine/AudioEngine.h"
#include "Engine/Exporter.h"
#include "Model/Params.h"
#include <juce_events/juce_events.h>

namespace tessera::test
{

constexpr double SR = 48000.0;
constexpr int BLOCK = 256;

// Renders `seconds` of audio through the engine in BLOCK-sized chunks.
inline juce::AudioBuffer<float> render (AudioEngine& e, double seconds, const juce::AudioBuffer<float>* input = nullptr)
{
    const int total = (int) std::round (seconds * SR);
    juce::AudioBuffer<float> out (2, total);
    juce::AudioBuffer<float> tmp (2, BLOCK);
    for (int done = 0; done < total; done += BLOCK)
    {
        const int n = juce::jmin (BLOCK, total - done);
        const float* ins[2] = { nullptr, nullptr };
        if (input) { ins[0] = input->getReadPointer (0, done); ins[1] = input->getReadPointer (1, done); }
        e.renderBlock (tmp.getArrayOfWritePointers(), 2, input ? ins : nullptr, input ? 2 : 0, n);
        out.copyFrom (0, done, tmp, 0, 0, n);
        out.copyFrom (1, done, tmp, 1, 0, n);
    }
    return out;
}

inline float rms (const juce::AudioBuffer<float>& b, double fromSec, double toSec)
{
    const int a = juce::jlimit (0, b.getNumSamples(), (int) (fromSec * SR));
    const int z = juce::jlimit (0, b.getNumSamples(), (int) (toSec * SR));
    if (z <= a) return 0.0f;
    return juce::jmax (b.getRMSLevel (0, a, z - a), b.getRMSLevel (1, a, z - a));
}

// First sample index whose magnitude exceeds `threshold` (or -1).
inline int onset (const juce::AudioBuffer<float>& b, float threshold = 0.01f)
{
    for (int i = 0; i < b.getNumSamples(); ++i)
        if (std::abs (b.getSample (0, i)) > threshold || std::abs (b.getSample (1, i)) > threshold) return i;
    return -1;
}

inline bool finite (const juce::AudioBuffer<float>& b)
{
    for (int c = 0; c < b.getNumChannels(); ++c)
        for (int i = 0; i < b.getNumSamples(); ++i)
            if (! std::isfinite (b.getSample (c, i))) return false;
    return true;
}

inline std::shared_ptr<Clip> midiClip (std::vector<Note> notes, double length = 4.0)
{
    auto c = std::make_shared<Clip>();
    c->id = Clip::newId();
    c->name = "Test";
    c->lengthBeats = length;
    c->notes = std::move (notes);
    return c;
}

// Empty 2-track project: track 0 drums, track 1 synth, at 120 bpm (1 beat = 0.5 s).
inline Project baseProject()
{
    Project p;
    p.tempo = 120.0;
    for (int i = 0; i < 4; ++i) p.scenes.push_back ({ juce::String (i + 1) });
    auto drums = makeTrack (TrackKind::midi, "Drums", 0);
    drums.instrument.type = InstrumentType::drums;
    drums.instrument.params = defaultsFor (drumParams());
    p.tracks.push_back (drums);
    p.tracks.push_back (makeTrack (TrackKind::midi, "Synth", 1));
    p.ensureSlotCount();
    return p;
}

inline void load (AudioEngine& e, const Project& p)
{
    e.setProject (std::make_shared<const Project> (p));
}

inline juce::File writeSineWav (double seconds, double freq, double rate = 44100.0)
{
    auto f = juce::File::createTempFile (".wav");
    juce::WavAudioFormat wav;
    std::unique_ptr<juce::OutputStream> os (f.createOutputStream());
    std::unique_ptr<juce::AudioFormatWriter> w (wav.createWriterFor (os.get(), rate, 2, 16, {}, 0));
    os.release();
    juce::AudioBuffer<float> b (2, (int) (seconds * rate));
    for (int i = 0; i < b.getNumSamples(); ++i)
    {
        const float v = 0.5f * (float) std::sin (juce::MathConstants<double>::twoPi * freq * i / rate);
        b.setSample (0, i, v);
        b.setSample (1, i, v);
    }
    w->writeFromAudioSampleBuffer (b, 0, b.getNumSamples());
    return f;
}

} // namespace tessera::test
