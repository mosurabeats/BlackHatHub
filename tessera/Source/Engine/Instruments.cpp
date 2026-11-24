#include "Instruments.h"

namespace tessera
{

// ================================================================== PolySynth

void PolySynth::prepare (double sampleRate, int maxBlock)
{
    sr = sampleRate;
    exchange.read (p);
    prepared = true;
    juce::dsp::ProcessSpec spec { sampleRate, (juce::uint32) juce::jmax (1, maxBlock), 1 };
    for (auto& v : voices)
    {
        v.amp.setSampleRate (sampleRate);
        v.filt.setSampleRate (sampleRate);
        v.filter.prepare (spec);
        v.filter.setType (juce::dsp::StateVariableTPTFilterType::lowpass);
        v.amp.setParameters (p.amp);
        v.filt.setParameters (p.filt);
    }
    reset();
}

void PolySynth::setParams (const InstrumentSettings& s)
{
    auto& d = synthParams();
    auto g = [&] (const char* k) { return paramValue (s.params, d, k); };
    P n;
    n.wave1 = (int) std::round (g ("osc1Wave"));
    n.wave2 = (int) std::round (g ("osc2Wave"));
    n.detune = g ("osc2Detune");
    n.level2 = g ("osc2Level");
    n.cutoff = g ("cutoff");
    n.reso = g ("resonance");
    n.envAmt = g ("envAmount");
    n.gain = juce::Decibels::decibelsToGain (g ("gain"));
    n.amp = { g ("attack"), g ("decay"), g ("sustain"), g ("release") };
    n.filt = { g ("attack") * 0.5f, g ("decay"), 0.0f, g ("release") };
    exchange.write (n);
    if (! prepared) { p = n; }
}

void PolySynth::reset()
{
    for (auto& v : voices) { v.amp.reset(); v.filt.reset(); v.filter.reset(); v.note = -1; }
}

void PolySynth::allNotesOff()
{
    for (auto& v : voices) if (v.note >= 0) { v.amp.noteOff(); v.filt.noteOff(); }
}

void PolySynth::noteOn (int note, float vel)
{
    Voice* target = nullptr;
    for (auto& v : voices) if (! v.active()) { target = &v; break; }
    if (target == nullptr)   // steal the oldest voice
    {
        target = &voices[0];
        for (auto& v : voices) if (v.age < target->age) target = &v;
    }
    auto& v = *target;
    v.note = note;
    v.velocity = vel;
    v.age = ++counter;
    const double f1 = juce::MidiMessage::getMidiNoteInHertz (note);
    const double f2 = f1 * std::pow (2.0, p.detune / 12.0);
    v.inc1 = f1 / sr;
    v.inc2 = f2 / sr;
    v.phase1 = v.phase2 = 0;
    v.filter.reset();
    v.amp.noteOn();
    v.filt.noteOn();
}

void PolySynth::noteOff (int note)
{
    for (auto& v : voices)
        if (v.note == note && v.active()) { v.amp.noteOff(); v.filt.noteOff(); }
}

static inline double polyBlep (double t, double dt)
{
    if (t < dt) { t /= dt; return t + t - t * t - 1.0; }
    if (t > 1.0 - dt) { t = (t - 1.0) / dt; return t * t + t + t + 1.0; }
    return 0.0;
}

float PolySynth::osc (int wave, double phase, double inc) const
{
    switch (wave)
    {
        case 0: return (float) std::sin (phase * juce::MathConstants<double>::twoPi);
        case 1: return (float) ((2.0 * phase - 1.0) - polyBlep (phase, inc));
        case 2:
        {
            double v = phase < 0.5 ? 1.0 : -1.0;
            v += polyBlep (phase, inc);
            v -= polyBlep (std::fmod (phase + 0.5, 1.0), inc);
            return (float) v;
        }
        default: return (float) (phase < 0.5 ? 4.0 * phase - 1.0 : 3.0 - 4.0 * phase);
    }
}

void PolySynth::render (int start, int num, juce::AudioBuffer<float>& out)
{
    auto* L = out.getWritePointer (0);
    auto* R = out.getWritePointer (1);
    for (auto& v : voices)
    {
        if (! v.active()) continue;
        for (int i = start; i < start + num; ++i)
        {
            if ((i & 15) == 0 || i == start)
            {
                const float env = v.filt.getNextSample();
                const float fc = juce::jlimit (30.0f, (float) (sr * 0.45), p.cutoff * std::pow (2.0f, p.envAmt * 6.0f * env));
                v.filter.setCutoffFrequency (fc);
                v.filter.setResonance (p.reso);
            }
            float s = osc (p.wave1, v.phase1, v.inc1) + p.level2 * osc (p.wave2, v.phase2, v.inc2);
            v.phase1 += v.inc1; if (v.phase1 >= 1.0) v.phase1 -= 1.0;
            v.phase2 += v.inc2; if (v.phase2 >= 1.0) v.phase2 -= 1.0;
            s = v.filter.processSample (0, s) * v.amp.getNextSample() * v.velocity * p.gain;
            L[i] += s;
            R[i] += s;
        }
        if (! v.active()) v.note = -1;
    }
}

void PolySynth::process (juce::AudioBuffer<float>& out, const juce::MidiBuffer& midi, int numSamples)
{
    if (exchange.read (p))
        for (auto& v : voices) { v.amp.setParameters (p.amp); v.filt.setParameters (p.filt); }
    int pos = 0;
    for (const auto meta : midi)
    {
        const int at = juce::jlimit (0, numSamples, meta.samplePosition);
        if (at > pos) { render (pos, at - pos, out); pos = at; }
        auto m = meta.getMessage();
        if (m.isNoteOn()) noteOn (m.getNoteNumber(), m.getFloatVelocity());
        else if (m.isNoteOff()) noteOff (m.getNoteNumber());
        else if (m.isAllNotesOff() || m.isAllSoundOff()) allNotesOff();
    }
    if (pos < numSamples) render (pos, numSamples - pos, out);
}

// ================================================================== DrumSampler

juce::String DrumSampler::padName (int pad)
{
    static const char* names[] = { "Kick", "Rim", "Snare", "Clap", "Snare 2", "Tom Lo", "Hat Closed", "Tom Mid",
                                   "Hat Pedal", "Tom Hi", "Hat Open", "Perc", "Cowbell", "Crash", "Shaker", "Ride" };
    return names[juce::jlimit (0, 15, pad)];
}

// Procedurally generated default kit so the sampler works with no sample files.
juce::AudioBuffer<float> DrumSampler::synthesizePad (int pad, double s)
{
    juce::Random rng (1234 + pad);
    auto make = [&] (double secs) { juce::AudioBuffer<float> b (1, juce::jmax (1, (int) (secs * s))); b.clear(); return b; };
    auto noise = [&] { return rng.nextFloat() * 2.0f - 1.0f; };
    juce::AudioBuffer<float> b;
    auto tone = [&] (double secs, double f0, double f1, double decay, float noiseAmt, double noiseDecay, double hpCoef)
    {
        b = make (secs);
        auto* d = b.getWritePointer (0);
        double ph = 0, prevIn = 0, hp = 0;
        for (int i = 0; i < b.getNumSamples(); ++i)
        {
            const double t = i / s;
            const double f = f1 + (f0 - f1) * std::exp (-t * 30.0);
            ph += f / s;
            double v = std::sin (ph * juce::MathConstants<double>::twoPi) * std::exp (-t / decay);
            double n = noise() * noiseAmt * std::exp (-t / noiseDecay);
            hp = hpCoef * (hp + n - prevIn); prevIn = n;      // one-pole high-pass on noise
            d[i] = (float) juce::jlimit (-1.0, 1.0, v + (hpCoef > 0 ? hp : n));
        }
    };
    switch (pad)
    {
        case 0:  tone (0.6, 160, 45, 0.25, 0.05f, 0.01, 0); break;               // kick
        case 1:  tone (0.08, 1700, 1700, 0.015, 0.5f, 0.01, 0.6); break;          // rim
        case 2:  tone (0.35, 240, 180, 0.08, 0.9f, 0.12, 0.7); break;             // snare
        case 3:  tone (0.4, 1000, 1000, 0.001, 1.0f, 0.09, 0.85); break;          // clap
        case 4:  tone (0.3, 300, 220, 0.06, 0.8f, 0.08, 0.8); break;              // snare 2
        case 5:  tone (0.5, 140, 90, 0.2, 0.05f, 0.02, 0); break;                 // tom lo
        case 6:  tone (0.08, 0, 0, 0.001, 0.9f, 0.025, 0.97); break;              // hat closed
        case 7:  tone (0.45, 200, 130, 0.18, 0.05f, 0.02, 0); break;              // tom mid
        case 8:  tone (0.12, 0, 0, 0.001, 0.8f, 0.04, 0.97); break;               // hat pedal
        case 9:  tone (0.4, 280, 180, 0.15, 0.05f, 0.02, 0); break;               // tom hi
        case 10: tone (0.5, 0, 0, 0.001, 0.8f, 0.22, 0.97); break;                // hat open
        case 11: tone (0.15, 900, 600, 0.04, 0.3f, 0.03, 0.5); break;             // perc
        case 12: tone (0.3, 800, 800, 0.08, 0.0f, 0.01, 0); break;                // cowbell
        case 13: tone (1.4, 0, 0, 0.001, 0.7f, 0.6, 0.95); break;                 // crash
        case 14: tone (0.12, 0, 0, 0.001, 0.6f, 0.05, 0.9); break;                // shaker
        default: tone (1.0, 3000, 3000, 0.3, 0.4f, 0.4, 0.96); break;             // ride
    }
    return b;
}

void DrumSampler::prepare (double sampleRate, int)
{
    sr = sampleRate;
    for (int i = 0; i < numPads; ++i) builtIn[(size_t) i] = synthesizePad (i, sampleRate);
    reset();
}

void DrumSampler::reset()
{
    for (auto& v : voices) v.pos = -1;
}

void DrumSampler::setParams (const InstrumentSettings& s)
{
    auto& d = drumParams();
    exchange.write ({ paramValue (s.params, d, "tune"), paramValue (s.params, d, "decay"),
                      juce::Decibels::decibelsToGain (paramValue (s.params, d, "gain")) });
    std::array<SampleBuffer, numPads> next;
    for (int i = 0; i < numPads; ++i)
        if (fileCache && s.padSamples[(size_t) i].isNotEmpty())
            next[(size_t) i] = fileCache->get (s.padSamples[(size_t) i], sr);
    const juce::SpinLock::ScopedLockType l (sampleLock);
    loaded.swap (next);   // old buffers are released here, on the message thread
}

void DrumSampler::process (juce::AudioBuffer<float>& out, const juce::MidiBuffer& midi, int numSamples)
{
    exchange.read (p);
    const juce::SpinLock::ScopedTryLockType l (sampleLock);
    if (! l.isLocked()) return;
    const double rate = std::pow (2.0, p.tune / 12.0);
    const float decay = p.decay, gain = p.gain;
    auto renderPad = [&] (int pad, int from, int to)
    {
        auto& v = voices[(size_t) pad];
        if (v.pos < 0) return;
        const juce::AudioBuffer<float>* buf = loaded[(size_t) pad] ? loaded[(size_t) pad].get() : &builtIn[(size_t) pad];
        const int len = buf->getNumSamples();
        const int chR = buf->getNumChannels() > 1 ? 1 : 0;
        const double fadeLen = len * juce::jlimit (0.05, 2.0, (double) decay);
        for (int i = from; i < to; ++i)
        {
            const int idx = (int) v.pos;
            if (idx >= len - 1 || v.pos >= fadeLen) { v.pos = -1; return; }
            const float frac = (float) (v.pos - idx);
            const float env = decay < 1.0f ? (float) (1.0 - v.pos / fadeLen) : 1.0f;
            const float g = v.vel * gain * env;
            out.getWritePointer (0)[i] += g * (buf->getSample (0, idx) * (1 - frac) + buf->getSample (0, idx + 1) * frac);
            out.getWritePointer (1)[i] += g * (buf->getSample (chR, idx) * (1 - frac) + buf->getSample (chR, idx + 1) * frac);
            v.pos += rate;
        }
    };
    int pos = 0;
    for (const auto meta : midi)
    {
        const int at = juce::jlimit (0, numSamples, meta.samplePosition);
        for (int p = 0; p < numPads; ++p) renderPad (p, pos, at);
        pos = at;
        auto m = meta.getMessage();
        if (m.isNoteOn())
        {
            const int pad = m.getNoteNumber() - baseNote;
            if (pad >= 0 && pad < numPads)
            {
                voices[(size_t) pad] = { 0.0, m.getFloatVelocity() };
                if (pad == 6 || pad == 8) voices[10].pos = -1;   // closed/pedal hat chokes open hat
            }
        }
    }
    for (int p = 0; p < numPads; ++p) renderPad (p, pos, numSamples);
}

std::unique_ptr<Instrument> createInstrument (InstrumentType t, AudioFileCache* cache)
{
    switch (t)
    {
        case InstrumentType::synth: return std::make_unique<PolySynth>();
        case InstrumentType::drums: return std::make_unique<DrumSampler> (cache);
        case InstrumentType::none: break;
    }
    return nullptr;
}

} // namespace tessera
