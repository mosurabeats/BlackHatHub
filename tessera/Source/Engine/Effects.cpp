#include "Effects.h"

namespace tessera
{

namespace
{
float pv (const EffectSettings& s, const char* k) { return paramValue (s.params, effectParams (s.type), k); }

juce::dsp::AudioBlock<float> blockOf (juce::AudioBuffer<float>& b, int n)
{
    return juce::dsp::AudioBlock<float> (b).getSubBlock (0, (size_t) n);
}

// ------------------------------------------------------------------ 3-band EQ
class Eq3 : public Effect
{
    struct P { float low = 0, mid = 0, midFreq = 1000, high = 0; };
    ParamExchange<P> ex; P p, applied { 99, 99, 99, 99 };
    double sr = 44100;
    std::array<juce::dsp::IIR::Filter<float>, 2> lo, mi, hi;

    void update()
    {
        auto l = juce::dsp::IIR::Coefficients<float>::makeLowShelf (sr, 200.0, 0.7071f, juce::Decibels::decibelsToGain (p.low));
        auto m = juce::dsp::IIR::Coefficients<float>::makePeakFilter (sr, juce::jlimit (20.0, sr * 0.45, (double) p.midFreq), 0.9f,
                                                                      juce::Decibels::decibelsToGain (p.mid));
        auto h = juce::dsp::IIR::Coefficients<float>::makeHighShelf (sr, juce::jmin (6000.0, sr * 0.4), 0.7071f, juce::Decibels::decibelsToGain (p.high));
        for (int c = 0; c < 2; ++c) { *lo[(size_t) c].coefficients = *l; *mi[(size_t) c].coefficients = *m; *hi[(size_t) c].coefficients = *h; }
        applied = p;
    }

public:
    void prepare (double sampleRate, int) override
    {
        sr = sampleRate;
        for (auto* arr : { &lo, &mi, &hi })
            for (auto& f : *arr) f.coefficients = new juce::dsp::IIR::Coefficients<float> (1, 0, 1, 0);
        ex.read (p);
        update();
        reset();
    }
    void setParams (const EffectSettings& s) override { ex.write ({ pv (s, "low"), pv (s, "mid"), pv (s, "midFreq"), pv (s, "high") }); }
    void reset() override { for (int c = 0; c < 2; ++c) { lo[(size_t) c].reset(); mi[(size_t) c].reset(); hi[(size_t) c].reset(); } }
    void process (juce::AudioBuffer<float>& b, int n, double) override
    {
        if (ex.read (p)) update();   // coefficient objects are pre-allocated: assignment does not allocate
        for (int c = 0; c < 2; ++c)
        {
            auto* d = b.getWritePointer (c);
            for (int i = 0; i < n; ++i)
                d[i] = hi[(size_t) c].processSample (mi[(size_t) c].processSample (lo[(size_t) c].processSample (d[i])));
        }
    }
};

// ------------------------------------------------------------------ Compressor
class Comp : public Effect
{
    struct P { float threshold = -18, ratio = 4, attack = 10, release = 120, makeup = 3; };
    ParamExchange<P> ex; P p;
    juce::dsp::Compressor<float> comp;
    void apply() { comp.setThreshold (p.threshold); comp.setRatio (juce::jmax (1.0f, p.ratio)); comp.setAttack (p.attack); comp.setRelease (p.release); }

public:
    void prepare (double sr, int maxBlock) override
    {
        comp.prepare ({ sr, (juce::uint32) juce::jmax (1, maxBlock), 2 });
        ex.read (p);
        apply();
    }
    void setParams (const EffectSettings& s) override
    {
        ex.write ({ pv (s, "threshold"), pv (s, "ratio"), pv (s, "attack"), pv (s, "release"), pv (s, "makeup") });
    }
    void reset() override { comp.reset(); }
    void process (juce::AudioBuffer<float>& b, int n, double) override
    {
        if (ex.read (p)) apply();
        auto blk = blockOf (b, n);
        comp.process (juce::dsp::ProcessContextReplacing<float> (blk));
        b.applyGain (0, n, juce::Decibels::decibelsToGain (p.makeup));
    }
};

// ------------------------------------------------------------------ Tempo-synced delay
class Delay : public Effect
{
    struct P { float time = 0.75f, feedback = 0.35f, mix = 0.25f; };
    ParamExchange<P> ex; P p;
    juce::AudioBuffer<float> line;
    int write = 0;
    double sr = 44100;
    float smoothedDelay = -1;

public:
    void prepare (double sampleRate, int) override
    {
        sr = sampleRate;
        line.setSize (2, (int) (sampleRate * 6.0) + 4);
        ex.read (p);
        reset();
    }
    void setParams (const EffectSettings& s) override { ex.write ({ pv (s, "time"), pv (s, "feedback"), pv (s, "mix") }); }
    void reset() override { line.clear(); write = 0; smoothedDelay = -1; }
    void process (juce::AudioBuffer<float>& b, int n, double tempo) override
    {
        ex.read (p);
        const int len = line.getNumSamples();
        const float target = (float) juce::jlimit (1.0, (double) len - 2, p.time * 60.0 / juce::jmax (20.0, tempo) * sr);
        if (smoothedDelay < 0) smoothedDelay = target;
        for (int i = 0; i < n; ++i)
        {
            smoothedDelay += (target - smoothedDelay) * 0.0005f;
            float rp = (float) write - smoothedDelay;
            if (rp < 0) rp += (float) len;
            const int i0 = (int) rp;
            const int i1 = (i0 + 1) % len;
            const float fr = rp - (float) i0;
            for (int c = 0; c < 2; ++c)
            {
                const float delayed = line.getSample (c, i0) * (1 - fr) + line.getSample (c, i1) * fr;
                const float in = b.getSample (c, i);
                line.setSample (c, write, in + delayed * p.feedback);
                b.setSample (c, i, in * (1 - p.mix) + delayed * p.mix);
            }
            if (++write >= len) write = 0;
        }
    }
};

// ------------------------------------------------------------------ Reverb
class Verb : public Effect
{
    struct P { float size = 0.5f, damping = 0.5f, width = 1, mix = 0.25f; };
    ParamExchange<P> ex; P p;
    juce::dsp::Reverb reverb;
    void apply()
    {
        juce::dsp::Reverb::Parameters rp;
        rp.roomSize = p.size; rp.damping = p.damping; rp.width = p.width;
        rp.wetLevel = p.mix; rp.dryLevel = 1.0f - p.mix;
        reverb.setParameters (rp);
    }

public:
    void prepare (double sr, int maxBlock) override { reverb.prepare ({ sr, (juce::uint32) juce::jmax (1, maxBlock), 2 }); ex.read (p); apply(); }
    void setParams (const EffectSettings& s) override { ex.write ({ pv (s, "size"), pv (s, "damping"), pv (s, "width"), pv (s, "mix") }); }
    void reset() override { reverb.reset(); }
    void process (juce::AudioBuffer<float>& b, int n, double) override
    {
        if (ex.read (p)) apply();
        auto blk = blockOf (b, n);
        reverb.process (juce::dsp::ProcessContextReplacing<float> (blk));
    }
};

// ------------------------------------------------------------------ Multimode filter
class Filt : public Effect
{
    struct P { float mode = 0, cutoff = 2000, resonance = 0.7f; };
    ParamExchange<P> ex; P p;
    juce::dsp::StateVariableTPTFilter<float> f;
    double sr = 44100;
    void apply()
    {
        const int m = juce::jlimit (0, 2, (int) std::round (p.mode));
        f.setType (m == 0 ? juce::dsp::StateVariableTPTFilterType::lowpass
                 : m == 1 ? juce::dsp::StateVariableTPTFilterType::highpass
                          : juce::dsp::StateVariableTPTFilterType::bandpass);
        f.setCutoffFrequency (juce::jlimit (20.0f, (float) (sr * 0.45), p.cutoff));
        f.setResonance (juce::jmax (0.1f, p.resonance));
    }

public:
    void prepare (double sampleRate, int maxBlock) override { sr = sampleRate; f.prepare ({ sr, (juce::uint32) juce::jmax (1, maxBlock), 2 }); ex.read (p); apply(); }
    void setParams (const EffectSettings& s) override { ex.write ({ pv (s, "mode"), pv (s, "cutoff"), pv (s, "resonance") }); }
    void reset() override { f.reset(); }
    void process (juce::AudioBuffer<float>& b, int n, double) override
    {
        if (ex.read (p)) apply();
        auto blk = blockOf (b, n);
        f.process (juce::dsp::ProcessContextReplacing<float> (blk));
    }
};
} // namespace

std::unique_ptr<Effect> createEffect (EffectType t)
{
    switch (t)
    {
        case EffectType::eq3: return std::make_unique<Eq3>();
        case EffectType::compressor: return std::make_unique<Comp>();
        case EffectType::delay: return std::make_unique<Delay>();
        case EffectType::reverb: return std::make_unique<Verb>();
        case EffectType::filter: return std::make_unique<Filt>();
    }
    return nullptr;
}

} // namespace tessera
