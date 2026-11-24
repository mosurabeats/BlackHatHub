#pragma once
// Tessera real-time engine.
//
// Threading model
// ---------------
// * The message thread builds an immutable EngineState (project snapshot + instrument/effect
//   processors + decoded audio) and hands it over with setProject(). The audio thread picks it
//   up with a try-lock and never frees anything: the previous state is handed back and released
//   on the message thread (collectGarbage()).
// * UI actions (launch clip, stop, play, live notes...) travel through a lock-free command FIFO.
// * Per-track session state (playing/queued slot) lives in TrackRuntime and is written only by
//   the audio thread; the UI reads it through atomics.
// * Recorded MIDI events flow back through a lock-free FIFO and are turned into clips on the
//   message thread by pollRecording().

#include "../Model/ProjectController.h"
#include "AudioFileCache.h"
#include "Effects.h"
#include "Instruments.h"
#include <juce_audio_devices/juce_audio_devices.h>
#include <atomic>
#include <map>
#include <set>
#include <vector>

namespace tessera
{

struct TrackRuntime
{
    std::atomic<int> playingSlot { -1 }, queuedSlot { -1 };
    std::atomic<bool> stopQueued { false };
    std::atomic<float> peakL { 0 }, peakR { 0 };
    std::atomic<double> clipPhase { 0 };      // 0..1 progress through the playing session clip
    std::atomic<int> recordingSlot { -1 };
    // audio-thread only
    double clipStartBeat = 0, launchAtBeat = 0, stopAtBeat = 0;
    double recStartBeat = 0, recEndBeat = 0;
    std::array<bool, 128> sounding {};
    bool panicPending = false;
};

struct TrackDevices
{
    std::shared_ptr<TrackRuntime> runtime;
    std::shared_ptr<Instrument> instrument;
    std::vector<std::shared_ptr<Effect>> effects;   // enabled effects, in chain order
    juce::AudioBuffer<float> buffer;                 // audio-thread scratch (pre-allocated)
    juce::MidiBuffer midi;
};

struct EngineState
{
    std::shared_ptr<const Project> project;
    std::vector<TrackDevices> tracks;               // parallel to project->tracks
    std::map<juce::String, SampleBuffer> audio;     // decoded audio by file path
};

class AudioEngine : public juce::AudioIODeviceCallback
{
public:
    AudioEngine();
    ~AudioEngine() override;

    // ----- setup (message thread)
    void prepare (double sampleRate, int maxBlockSize);
    void setProject (std::shared_ptr<const Project> p);
    void collectGarbage();
    AudioFileCache& fileCache() { return cache; }
    double sampleRate() const { return sr; }

    // ----- transport & session control (any thread; queued to the audio thread)
    void play();
    void stop();                       // stops transport; stops session clips; resets to loop/zero on second stop
    void locate (double beat);
    void launchClip (int track, int slot);
    void stopTrack (int track);
    void launchScene (int slot);
    void stopAllClips();
    void noteOn (int track, int note, float velocity);
    void noteOff (int track, int note);
    void recordIntoSlot (int track, int slot, double lengthBeats);

    // ----- arrangement recording (message thread)
    bool startRecording (juce::String& error);   // records armed tracks from the current position
    void stopRecording (ProjectController& controller);
    bool isRecording() const { return recording.load(); }
    void pollRecording (ProjectController& controller);   // call ~30x per second

    // ----- state for the UI (any thread)
    bool isPlaying() const { return playing.load(); }
    double positionBeats() const { return position.load(); }
    const TrackRuntime* runtimeFor (int trackIndex) const;
    float masterPeakL() const { return masterL.load(); }
    float masterPeakR() const { return masterR.load(); }

    // ----- rendering (audio thread, or offline)
    void renderBlock (float* const* outputs, int numOutputs, const float* const* inputs, int numInputs, int numSamples);

    // AudioIODeviceCallback
    void audioDeviceIOCallbackWithContext (const float* const* in, int numIn, float* const* out, int numOut, int numSamples,
                                           const juce::AudioIODeviceCallbackContext&) override;
    void audioDeviceAboutToStart (juce::AudioIODevice* device) override;
    void audioDeviceStopped() override {}

    static double quantizedLaunchBeat (double now, double quantBeats, bool transportRunning);

private:
    struct Cmd
    {
        enum Type { Play, Stop, Locate, Launch, StopTrack, LaunchScene, StopAll, NoteOn, NoteOff, RecordSlot, LaunchAligned } type;
        int track = -1, slot = -1, note = 0;
        float velocity = 0;
        double beat = 0;
    };
    struct RecEvent
    {
        enum Type { On, Off, SlotDone } type;
        int track = -1, slot = -1, note = 0;
        float velocity = 0;
        double beat = 0;      // absolute beat (arrangement) or beat relative to slot record start
    };

    void push (const Cmd& c);
    void pushRec (const RecEvent& e);
    void handleCommands (EngineState& st);
    void renderTrackRange (EngineState& st, int ti, double b0, double b1, int offset, int len, double bps, bool transportMoving);
    void emitMidiClip (TrackRuntime& rt, juce::MidiBuffer& midi, const Clip& clip, double clipStart, bool loop,
                       double r0, double r1, double b0, int offset, int len, double bps, double hardEnd);
    void emitAudioClip (const EngineState& st, juce::AudioBuffer<float>& buf, const Clip& clip, double clipStart, bool loop,
                        double r0, double r1, double b0, int offset, int len, double bps, double tempo);
    void allOff (TrackRuntime& rt, juce::MidiBuffer& midi, int sample);
    std::shared_ptr<Instrument> instrumentFor (const Track& t);
    std::shared_ptr<Effect> effectFor (const EffectSettings& e);

    double sr = 44100;
    int maxBlock = 512;
    AudioFileCache cache;

    // state handover
    juce::SpinLock stateLock;
    std::shared_ptr<EngineState> pending, active, retired;
    std::shared_ptr<EngineState> latest;   // message-thread copy

    // message-thread caches (persist processors across snapshots)
    std::map<juce::String, std::shared_ptr<TrackRuntime>> runtimes;
    std::map<juce::String, std::pair<InstrumentType, std::shared_ptr<Instrument>>> instruments;
    std::map<juce::String, std::pair<EffectType, std::shared_ptr<Effect>>> effects;

    // commands
    juce::AbstractFifo cmdFifo { 1024 };
    std::array<Cmd, 1024> cmdBuf;
    juce::SpinLock cmdWriteLock;

    // recording
    juce::AbstractFifo recFifo { 8192 };
    std::array<RecEvent, 8192> recBuf;
    std::atomic<bool> recording { false };
    double recordStartBeat = 0;
    juce::SpinLock writerLock;
    std::unique_ptr<juce::AudioFormatWriter::ThreadedWriter> audioWriter;
    juce::TimeSliceThread writerThread { "Tessera audio recorder" };
    juce::File recordingFile;
    int recordingAudioTrack = -1;
    std::map<std::pair<int, int>, std::pair<double, float>> openNotes;            // (track,note) -> (start, vel)
    std::map<int, std::vector<Note>> recordedNotes;                                 // track -> notes (absolute beats)
    std::map<std::pair<int, int>, std::vector<Note>> slotNotes;                     // (track,slot) -> notes (relative)
    std::map<std::pair<int, int>, double> slotLengths;

    // transport (audio thread owns, UI reads)
    std::atomic<bool> playing { false };
    std::atomic<double> position { 0 };
    std::atomic<float> masterL { 0 }, masterR { 0 };

    // scratch buffers (allocated in prepare)
    juce::AudioBuffer<float> master;
    juce::AudioBuffer<float> clickHi, clickLo;
    int clickIdx = -1, clickDelay = 0;
    bool clickAccent = false;
};

} // namespace tessera
