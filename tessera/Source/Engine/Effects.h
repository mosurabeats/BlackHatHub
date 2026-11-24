#pragma once
#include "../Model/Params.h"
#include "ParamExchange.h"
#include <juce_dsp/juce_dsp.h>

namespace tessera
{

// Stereo insert effect. setParams() is called on the message thread; process() on the audio thread.
class Effect
{
public:
    virtual ~Effect() = default;
    virtual void prepare (double sampleRate, int maxBlock) = 0;
    virtual void setParams (const EffectSettings& s) = 0;
    virtual void process (juce::AudioBuffer<float>& buf, int numSamples, double tempo) = 0;
    virtual void reset() = 0;
};

std::unique_ptr<Effect> createEffect (EffectType t);

} // namespace tessera
