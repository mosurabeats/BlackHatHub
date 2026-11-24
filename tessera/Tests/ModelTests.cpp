#include "TestHelpers.h"

using namespace tessera;
using namespace tessera::test;

class ModelTests : public juce::UnitTest
{
public:
    ModelTests() : juce::UnitTest ("Model", "Tessera") {}

    void runTest() override
    {
        beginTest ("Default project");
        {
            auto p = Project::createDefault();
            expectEquals ((int) p.tracks.size(), 3);
            expectEquals ((int) p.scenes.size(), 8);
            for (auto& t : p.tracks) expectEquals ((int) t.slots.size(), 8);
            expect (p.tracks[0].instrument.type == InstrumentType::drums);
        }

        beginTest ("Demo project is well formed");
        {
            auto p = Project::createDemo();
            expectEquals ((int) p.tracks.size(), 4);
            expect (p.arrangementEndBeat() == 64.0);
            for (auto& t : p.tracks) expectEquals ((int) t.slots.size(), (int) p.scenes.size());
            AudioEngine e; e.prepare (SR, BLOCK); load (e, p);
            e.launchScene (2);
            auto out = render (e, 2.0);
            expect (finite (out) && rms (out, 0.0, 2.0) > 0.01f && out.getMagnitude (0, out.getNumSamples()) < 4.0f);
        }

        beginTest ("Save / load round trip preserves everything");
        {
            auto p = baseProject();
            p.tempo = 97.5; p.loopEnabled = true; p.loopStart = 2; p.loopEnd = 10; p.metronome = true;
            p.tracks[1].volumeDb = -6.5f; p.tracks[1].pan = 0.25f; p.tracks[1].mute = true;
            p.tracks[1].instrument.params["cutoff"] = 777.0f;
            p.tracks[1].effects.push_back (makeEffect (EffectType::delay));
            p.tracks[1].effects[0].params["feedback"] = 0.6f;
            p.tracks[1].effects[0].enabled = false;
            p.tracks[0].instrument.padSamples[3] = "/tmp/clap.wav";
            p.tracks[1].slots[2] = midiClip ({ { 60, 0.5, 1.25, 0.7f }, { 64, 0.0, 0.5, 1.0f } }, 8.0);
            p.tracks[0].arrangement.push_back ({ midiClip ({ { 36, 0, 0.5, 1.0f } }), 16.0, 8.0 });
            auto f = juce::File::createTempFile (".tessera");
            juce::String err;
            expect (p.saveTo (f, err), err);
            Project q;
            expect (Project::loadFrom (f, q, err), err);
            expectEquals (q.tempo, 97.5);
            expect (q.loopEnabled && q.loopStart == 2 && q.loopEnd == 10 && q.metronome);
            expectEquals (q.tracks[1].volumeDb, -6.5f);
            expectEquals (q.tracks[1].pan, 0.25f);
            expect (q.tracks[1].mute);
            expectEquals (q.tracks[1].instrument.params["cutoff"], 777.0f);
            expectEquals ((int) q.tracks[1].effects.size(), 1);
            expect (q.tracks[1].effects[0].type == EffectType::delay && ! q.tracks[1].effects[0].enabled);
            expectEquals (q.tracks[1].effects[0].params["feedback"], 0.6f);
            expectEquals (q.tracks[0].instrument.padSamples[3], juce::String ("/tmp/clap.wav"));
            expect (q.tracks[1].slots[2] != nullptr);
            expectEquals ((int) q.tracks[1].slots[2]->notes.size(), 2);
            expectEquals (q.tracks[1].slots[2]->notes[0].pitch, 64);   // sorted by start
            expectEquals (q.tracks[1].slots[2]->lengthBeats, 8.0);
            expectEquals ((int) q.tracks[0].arrangement.size(), 1);
            expectEquals (q.tracks[0].arrangement[0].startBeat, 16.0);
            expectEquals (q.tracks[0].id, p.tracks[0].id);
            f.deleteFile();
        }

        beginTest ("Invalid files are rejected with a message");
        {
            auto f = juce::File::createTempFile (".tessera");
            f.replaceWithText ("{ not json");
            Project q; juce::String err;
            expect (! Project::loadFrom (f, q, err) && err.isNotEmpty());
            f.replaceWithText ("{\"format\": \"something-else\"}");
            err = {};
            expect (! Project::loadFrom (f, q, err) && err.contains ("Not a Tessera"));
            f.deleteFile();
        }

        beginTest ("Undo / redo");
        {
            juce::ScopedJuceInitialiser_GUI init;
            ProjectController c;
            const double t0 = c.project().tempo;
            c.edit ("Tempo", [] (Project& p) { p.tempo = 140; });
            c.edit ("Add track", [] (Project& p) { p.tracks.push_back (makeTrack (TrackKind::midi, "New", 5)); });
            expectEquals ((int) c.project().tracks.size(), 4);
            expectEquals ((int) c.project().tracks.back().slots.size(), 8);   // slots auto-sized
            expect (c.undo());
            expectEquals ((int) c.project().tracks.size(), 3);
            expect (c.undo());
            expectEquals (c.project().tempo, t0);
            expect (! c.undo());
            expect (c.redo());
            expectEquals (c.project().tempo, 140.0);
            c.edit ("Other", [] (Project& p) { p.tempo = 90; });
            expect (! c.canRedo(), "new edit clears redo");
        }

        beginTest ("Snapshots are immutable copies");
        {
            juce::ScopedJuceInitialiser_GUI init;
            ProjectController c;
            auto snap = c.snapshot();
            c.edit ("Tempo", [] (Project& p) { p.tempo = 150; });
            expectEquals (snap->tempo, 120.0);
            expectEquals (c.snapshot()->tempo, 150.0);
        }
    }
};

static ModelTests modelTests;
