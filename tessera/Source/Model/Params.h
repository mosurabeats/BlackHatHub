#pragma once
// Parameter definitions shared by the model (defaults), engine (ranges) and UI (sliders).
#include "Project.h"

namespace tessera
{

struct ParamDef
{
    const char* key;
    const char* label;
    float min, max, def;
    float skewCentre = 0.0f;   // 0 = linear; otherwise value shown at slider centre
    const char* suffix = "";
};

inline const std::vector<ParamDef>& synthParams()
{
    static const std::vector<ParamDef> p {
        { "osc1Wave", "Osc 1 wave", 0, 3, 1, 0, "" },          // 0 sine 1 saw 2 square 3 triangle
        { "osc2Wave", "Osc 2 wave", 0, 3, 2, 0, "" },
        { "osc2Detune", "Osc 2 detune", -24, 24, 7, 0, " st" },
        { "osc2Level", "Osc 2 level", 0, 1, 0.35f, 0, "" },
        { "cutoff", "Filter cutoff", 40, 18000, 3200, 1200, " Hz" },
        { "resonance", "Resonance", 0.1f, 4.0f, 0.7f, 0, "" },
        { "envAmount", "Filter env", 0, 1, 0.4f, 0, "" },
        { "attack", "Attack", 0.001f, 4, 0.01f, 0.3f, " s" },
        { "decay", "Decay", 0.01f, 4, 0.3f, 0.5f, " s" },
        { "sustain", "Sustain", 0, 1, 0.7f, 0, "" },
        { "release", "Release", 0.01f, 6, 0.4f, 0.6f, " s" },
        { "gain", "Gain", -36, 6, -8, 0, " dB" },
    };
    return p;
}

inline const std::vector<ParamDef>& drumParams()
{
    static const std::vector<ParamDef> p {
        { "tune", "Tune", -12, 12, 0, 0, " st" },
        { "decay", "Decay", 0.05f, 2.0f, 1.0f, 0, "x" },
        { "gain", "Gain", -36, 6, -4, 0, " dB" },
    };
    return p;
}

inline const std::vector<ParamDef>& effectParams (EffectType t)
{
    static const std::vector<ParamDef> eq {
        { "low", "Low", -18, 18, 0, 0, " dB" }, { "mid", "Mid", -18, 18, 0, 0, " dB" },
        { "midFreq", "Mid freq", 200, 8000, 1000, 1000, " Hz" }, { "high", "High", -18, 18, 0, 0, " dB" } };
    static const std::vector<ParamDef> comp {
        { "threshold", "Threshold", -60, 0, -18, 0, " dB" }, { "ratio", "Ratio", 1, 20, 4, 4, ":1" },
        { "attack", "Attack", 0.1f, 100, 10, 10, " ms" }, { "release", "Release", 10, 1000, 120, 150, " ms" },
        { "makeup", "Makeup", 0, 24, 3, 0, " dB" } };
    static const std::vector<ParamDef> delay {
        { "time", "Time (beats)", 0.125f, 2.0f, 0.75f, 0, "" }, { "feedback", "Feedback", 0, 0.95f, 0.35f, 0, "" },
        { "mix", "Dry/Wet", 0, 1, 0.25f, 0, "" } };
    static const std::vector<ParamDef> reverb {
        { "size", "Size", 0, 1, 0.5f, 0, "" }, { "damping", "Damping", 0, 1, 0.5f, 0, "" },
        { "width", "Width", 0, 1, 1.0f, 0, "" }, { "mix", "Dry/Wet", 0, 1, 0.25f, 0, "" } };
    static const std::vector<ParamDef> filter {
        { "mode", "Mode (LP/HP/BP)", 0, 2, 0, 0, "" }, { "cutoff", "Cutoff", 20, 20000, 2000, 1000, " Hz" },
        { "resonance", "Resonance", 0.1f, 8, 0.7f, 0, "" } };
    switch (t)
    {
        case EffectType::eq3: return eq;
        case EffectType::compressor: return comp;
        case EffectType::delay: return delay;
        case EffectType::reverb: return reverb;
        case EffectType::filter: return filter;
    }
    return eq;
}

inline std::map<juce::String, float> defaultsFor (const std::vector<ParamDef>& defs)
{
    std::map<juce::String, float> m;
    for (auto& d : defs) m[d.key] = d.def;
    return m;
}

inline float paramValue (const std::map<juce::String, float>& m, const std::vector<ParamDef>& defs, const char* key)
{
    if (auto it = m.find (key); it != m.end()) return it->second;
    for (auto& d : defs) if (juce::String (d.key) == key) return d.def;
    return 0.0f;
}

} // namespace tessera
