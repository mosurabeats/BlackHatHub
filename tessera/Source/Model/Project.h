#pragma once
// Tessera project model.
//
// The model is a plain value type. Clips are immutable once published (shared_ptr<const Clip>),
// so copying a Project is cheap and the audio thread can read a snapshot without locks.
// All musical times are in BEATS (quarter notes).

#include <juce_core/juce_core.h>
#include <juce_graphics/juce_graphics.h>
#include <array>
#include <map>
#include <memory>
#include <vector>

namespace tessera
{

struct Note
{
    int pitch = 60;           // MIDI note number
    double start = 0.0;       // beats from clip start
    double length = 1.0;      // beats
    float velocity = 0.8f;    // 0..1

    bool operator== (const Note&) const = default;
};

enum class ClipKind { midi, audio };

struct Clip
{
    juce::String id;
    juce::String name;
    ClipKind kind = ClipKind::midi;
    juce::Colour colour { 0xff4fb0a5 };
    double lengthBeats = 4.0;  // loop length
    bool looping = true;
    std::vector<Note> notes;   // midi clips (sorted by start)

    // audio clips
    juce::String audioFile;    // absolute path
    double sourceTempo = 120.0;// tempo the audio was played at (for re-pitch warping)
    bool warp = true;          // true: follow project tempo by re-pitching; false: play at native speed
    float gainDb = 0.0f;

    static juce::String newId();
};

using ClipPtr = std::shared_ptr<const Clip>;

enum class InstrumentType { none, synth, drums };

struct InstrumentSettings
{
    InstrumentType type = InstrumentType::synth;
    std::map<juce::String, float> params;          // see Instruments.h for keys/ranges
    std::array<juce::String, 16> padSamples;       // drum pads (empty = built-in synthesized sound)
};

enum class EffectType { eq3, compressor, delay, reverb, filter };

struct EffectSettings
{
    juce::String id;
    EffectType type = EffectType::eq3;
    bool enabled = true;
    std::map<juce::String, float> params;          // see Effects.h for keys/ranges
};

enum class TrackKind { midi, audio };

struct Placement
{
    ClipPtr clip;
    double startBeat = 0.0;
    double lengthBeats = 4.0;   // may exceed clip length (looping) or cut it short
};

struct Track
{
    juce::String id;
    juce::String name;
    TrackKind kind = TrackKind::midi;
    juce::Colour colour { 0xff4fb0a5 };
    float volumeDb = 0.0f;
    float pan = 0.0f;           // -1..1
    bool mute = false, solo = false, arm = false;
    InstrumentSettings instrument;
    std::vector<EffectSettings> effects;
    std::vector<ClipPtr> slots;          // session slots, one per scene (nullptr = empty)
    std::vector<Placement> arrangement;  // timeline clips
};

struct Scene
{
    juce::String name;
};

struct Project
{
    double tempo = 120.0;
    int beatsPerBar = 4;
    int launchQuantizeBars = 1;     // 0 = immediate
    float masterVolumeDb = 0.0f;
    bool metronome = false;
    double loopStart = 0.0, loopEnd = 16.0;
    bool loopEnabled = false;
    std::vector<Scene> scenes;
    std::vector<Track> tracks;

    // ----- helpers
    static Project createDefault();
    static Project createDemo();     // original example content to try the app immediately
    Track* findTrack (const juce::String& id);
    const Track* findTrack (const juce::String& id) const;
    int trackIndex (const juce::String& id) const;
    double arrangementEndBeat() const;
    void ensureSlotCount();          // every track has scenes.size() slots

    juce::var toVar() const;
    static Project fromVar (const juce::var& v, juce::String& error);
    bool saveTo (const juce::File& f, juce::String& error) const;
    static bool loadFrom (const juce::File& f, Project& out, juce::String& error);
};

Track makeTrack (TrackKind kind, const juce::String& name, int index);
EffectSettings makeEffect (EffectType type);
juce::String effectTypeName (EffectType t);
juce::Colour paletteColour (int index);

} // namespace tessera
