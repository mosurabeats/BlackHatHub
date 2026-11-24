#pragma once
#include "../Model/Params.h"
#include "AudioFileCache.h"
#include "ParamExchange.h"
#include <juce_dsp/juce_dsp.h>
#include <array>

namespace tessera
{

// Real-time instrument interface. process() renders numSamples into `out` (added, not replaced),
// applying MIDI events at their sample offsets. No allocation happens in process().
class Instrument
{
public:
    virtual ~Instrument() = default;
    virtual void prepare (double sampleRate, int maxBlock) = 0;
    virtual void setParams (const InstrumentSettings& s) = 0;
    virtual void process (juce::AudioBuffer<float>& out, const juce::MidiBuffer& midi, int numSamples) = 0;
    virtual void allNotesOff() = 0;
    virtual void reset() = 0;
};

// ------------------------------------------------------------------ subtractive polysynth

class PolySynth : public Instrument
{
public:
    static constexpr int numVoices = 12;
    void prepare (double sampleRate, int maxBlock) override;
    void setParams (const InstrumentSettings& s) override;
    void process (juce::AudioBuffer<float>& out, const juce::MidiBuffer& midi, int numSamples) override;
    void allNotesOff() override;
    void reset() override;

private:
    struct Voice
    {
        int note = -1;
        float velocity = 0;
        double phase1 = 0, phase2 = 0, inc1 = 0, inc2 = 0;
        juce::ADSR amp, filt;
        juce::dsp::StateVariableTPTFilter<float> filter;
        juce::uint32 age = 0;
        bool active() const { return amp.isActive(); }
    };
    void noteOn (int note, float vel);
    void noteOff (int note);
    void render (int start, int num, juce::AudioBuffer<float>& out);
    float osc (int wave, double phase, double inc) const;

    struct P
    {
        int wave1 = 1, wave2 = 2;
        float detune = 7, level2 = 0.35f, cutoff = 3200, reso = 0.7f, envAmt = 0.4f, gain = 0.4f;
        juce::ADSR::Parameters amp, filt;
    };
    std::array<Voice, numVoices> voices;
    double sr = 44100;
    juce::uint32 counter = 0;
    ParamExchange<P> exchange;   // message thread -> audio thread
    P p;                         // audio-thread copy
    bool prepared = false;
};

// ------------------------------------------------------------------ 16-pad drum sampler

class DrumSampler : public Instrument
{
public:
    static constexpr int numPads = 16;
    static constexpr int baseNote = 36;   // C1 (GM kick)

    explicit DrumSampler (AudioFileCache* cache) : fileCache (cache) {}
    void prepare (double sampleRate, int maxBlock) override;
    void setParams (const InstrumentSettings& s) override;   // call on message thread (loads samples)
    void process (juce::AudioBuffer<float>& out, const juce::MidiBuffer& midi, int numSamples) override;
    void allNotesOff() override {}
    void reset() override;
    static juce::String padName (int pad);
    static juce::AudioBuffer<float> synthesizePad (int pad, double sampleRate);

private:
    struct PadVoice { double pos = -1; float vel = 0; };
    AudioFileCache* fileCache;
    double sr = 44100;
    std::array<juce::AudioBuffer<float>, numPads> builtIn;
    std::array<SampleBuffer, numPads> loaded;
    std::array<PadVoice, numPads> voices;
    struct P { float tune = 0, decay = 1, gain = 0.6f; };
    ParamExchange<P> exchange;
    P p;
    juce::SpinLock sampleLock;
};

std::unique_ptr<Instrument> createInstrument (InstrumentType t, AudioFileCache* cache);

} // namespace tessera
