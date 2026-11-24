#include "TestHelpers.h"

using namespace tessera;
using namespace tessera::test;

// 120 bpm => 1 beat = 0.5 s = 24000 samples at 48 kHz.
static constexpr int beatSamples = 24000;

class EngineTests : public juce::UnitTest
{
public:
    EngineTests() : juce::UnitTest ("Engine", "Tessera") {}

    void runTest() override
    {
        beginTest ("Silence when stopped with an empty project");
        {
            AudioEngine e; e.prepare (SR, BLOCK); load (e, baseProject());
            auto out = render (e, 0.5);
            expectEquals (out.getMagnitude (0, out.getNumSamples()), 0.0f);
            expect (! e.isPlaying());
        }

        beginTest ("Launching a session clip starts the transport and makes sound");
        {
            auto p = baseProject();
            p.tracks[1].slots[0] = midiClip ({ { 60, 0.0, 1.0, 0.9f } });
            AudioEngine e; e.prepare (SR, BLOCK); load (e, p);
            e.launchClip (1, 0);
            auto out = render (e, 1.0);
            expect (e.isPlaying());
            expect (rms (out, 0.0, 0.5) > 0.01f, "note audible in first beat");
            expect (e.runtimeFor (1)->playingSlot.load() == 0);
            const int on = onset (out, 0.001f);
            expect (on >= 0 && on < 200, "starts immediately when transport was stopped (onset " + juce::String (on) + ")");
        }

        beginTest ("Clip launch is quantized to the next bar while playing");
        {
            auto p = baseProject();
            p.tracks[0].slots[0] = midiClip ({ { 36, 0.0, 0.5, 1.0f } });   // kick at clip start
            AudioEngine e; e.prepare (SR, BLOCK); load (e, p);
            e.play();
            render (e, 0.25);                       // now at beat 0.5
            e.launchClip (0, 0);
            auto out = render (e, 2.5);             // to beat 5.5
            const int on = onset (out, 0.01f) + (int) (0.25 * SR);
            expectWithinAbsoluteError (on, 4 * beatSamples, 64);   // bar 2 starts at beat 4
        }

        beginTest ("Scene launch starts every clip in the row; stop-all stops at the next bar");
        {
            auto p = baseProject();
            p.tracks[0].slots[1] = midiClip ({ { 36, 0.0, 0.5, 1.0f } });
            p.tracks[1].slots[1] = midiClip ({ { 64, 0.0, 4.0, 0.8f } });
            AudioEngine e; e.prepare (SR, BLOCK); load (e, p);
            e.launchScene (1);
            render (e, 0.1);
            expect (e.runtimeFor (0)->playingSlot.load() == 1 && e.runtimeFor (1)->playingSlot.load() == 1);
            e.stopAllClips();
            render (e, 1.0);                        // beat ~2.2: still playing until the bar
            expect (e.runtimeFor (1)->playingSlot.load() == 1);
            render (e, 1.2);                        // past beat 4
            expect (e.runtimeFor (0)->playingSlot.load() == -1 && e.runtimeFor (1)->playingSlot.load() == -1);
        }

        beginTest ("Session clip loops");
        {
            auto p = baseProject();
            p.tracks[0].slots[0] = midiClip ({ { 36, 0.0, 0.25, 1.0f } }, 2.0);   // kick every 2 beats (1 s)
            AudioEngine e; e.prepare (SR, BLOCK); load (e, p);
            e.launchClip (0, 0);
            auto out = render (e, 2.5);
            expect (rms (out, 0.0, 0.1) > 0.02f);
            expect (rms (out, 0.7, 0.95) < rms (out, 1.0, 1.1), "retrigger at 1.0 s");
            expect (rms (out, 2.0, 2.1) > 0.02f, "third iteration");
        }

        beginTest ("Arrangement clip plays at its timeline position");
        {
            auto p = baseProject();
            p.tracks[0].arrangement.push_back ({ midiClip ({ { 36, 0.0, 0.5, 1.0f } }), 8.0, 4.0 });
            AudioEngine e; e.prepare (SR, BLOCK); load (e, p);
            e.play();
            auto out = render (e, 5.0);
            expectWithinAbsoluteError (onset (out, 0.01f), 8 * beatSamples, 64);
        }

        beginTest ("Session clip overrides the arrangement on its track");
        {
            auto p = baseProject();
            p.tracks[1].arrangement.push_back ({ midiClip ({ { 48, 0.0, 4.0, 1.0f } }), 0.0, 4.0 });
            AudioEngine e; e.prepare (SR, BLOCK); load (e, p);
            e.play();
            auto withArr = render (e, 0.5);
            expect (rms (withArr, 0.1, 0.5) > 0.01f);
            p.tracks[1].slots[0] = midiClip ({}, 4.0);   // empty clip
            load (e, p);
            e.launchClip (1, 0);   // quantized to beat 4
            render (e, 2.0);
            auto after = render (e, 1.0);
            expect (rms (after, 0.5, 1.0) < 0.002f, "arrangement silenced while session clip plays");
        }

        beginTest ("Loop region wraps playback");
        {
            auto p = baseProject();
            p.loopEnabled = true; p.loopStart = 0; p.loopEnd = 4;
            p.tracks[0].arrangement.push_back ({ midiClip ({ { 36, 0.0, 0.25, 1.0f } }), 0.0, 4.0 });
            AudioEngine e; e.prepare (SR, BLOCK); load (e, p);
            e.play();
            auto out = render (e, 2.6);
            expect (rms (out, 1.6, 1.95) < rms (out, 2.0, 2.15), "kick retriggers at loop start (2.0 s)");
            expect (e.positionBeats() < 4.0);
        }

        beginTest ("Audio clips play, follow tempo when warped, and play natively when not");
        {
            auto wavFile = writeSineWav (1.0, 440.0);   // 1 s = 2 beats at 120 bpm
            auto clip = std::make_shared<Clip>();
            clip->id = Clip::newId(); clip->kind = ClipKind::audio; clip->audioFile = wavFile.getFullPathName();
            clip->sourceTempo = 120.0; clip->lengthBeats = 2.0; clip->looping = false;
            auto p = baseProject();
            p.tracks.push_back (makeTrack (TrackKind::audio, "Audio", 2));
            p.tempo = 240.0;   // twice as fast: 2 beats now last 0.5 s
            p.tracks[2].arrangement.push_back ({ clip, 0.0, 2.0 });
            p.ensureSlotCount();
            AudioEngine e; e.prepare (SR, BLOCK); load (e, p);
            e.play();
            auto out = render (e, 1.0);
            expect (rms (out, 0.05, 0.45) > 0.1f, "audio audible");
            expect (rms (out, 0.55, 0.95) < 0.001f, "warped clip ends after 0.5 s at 240 bpm");

            auto unwarped = std::make_shared<Clip> (*clip);
            unwarped->warp = false; unwarped->lengthBeats = 4.0;   // 4 beats at 240 bpm = 1 s
            p.tracks[2].arrangement[0] = { unwarped, 0.0, 4.0 };
            AudioEngine e2; e2.prepare (SR, BLOCK); load (e2, p);
            e2.play();
            auto out2 = render (e2, 1.2);
            expect (rms (out2, 0.6, 0.9) > 0.1f, "unwarped clip keeps native length (1 s)");
            wavFile.deleteFile();
        }

        beginTest ("Mute and solo");
        {
            auto p = baseProject();
            p.tracks[0].slots[0] = midiClip ({ { 36, 0.0, 0.5, 1.0f } });
            p.tracks[1].slots[0] = midiClip ({ { 60, 0.0, 4.0, 1.0f } });
            p.tracks[1].solo = true;
            AudioEngine e; e.prepare (SR, BLOCK); load (e, p);
            e.launchScene (0);
            render (e, 0.3);
            expect (e.runtimeFor (0)->peakL.load() == 0.0f, "non-solo track silent");
            expect (e.runtimeFor (1)->peakL.load() > 0.0f, "solo track audible");
            p.tracks[1].solo = false; p.tracks[1].mute = true;
            load (e, p);
            render (e, 0.5);
            expect (e.runtimeFor (1)->peakL.load() < 0.05f, "muted track decays to silence");
        }

        beginTest ("Every effect processes audio without producing NaN/Inf; reverb and delay have tails");
        {
            for (auto t : { EffectType::eq3, EffectType::compressor, EffectType::delay, EffectType::reverb, EffectType::filter })
            {
                auto fx = createEffect (t);
                fx->prepare (SR, BLOCK);
                auto settings = makeEffect (t);
                for (auto& [k, v] : settings.params) v = v * 1.3f;   // push params off-default
                fx->setParams (settings);
                juce::Random rng (7);
                juce::AudioBuffer<float> b (2, BLOCK);
                float tail = 0;
                for (int blk = 0; blk < 200; ++blk)
                {
                    for (int c = 0; c < 2; ++c)
                        for (int i = 0; i < BLOCK; ++i) b.setSample (c, i, blk < 20 ? rng.nextFloat() - 0.5f : 0.0f);
                    fx->process (b, BLOCK, 120.0);
                    expect (finite (b), effectTypeName (t) + " finite");
                    if (blk >= 25) tail = juce::jmax (tail, b.getMagnitude (0, BLOCK));
                }
                if (t == EffectType::reverb || t == EffectType::delay)
                    expect (tail > 1e-4f, effectTypeName (t) + " has a tail");
            }
        }

        beginTest ("Track effect chain is applied (filter darkens the synth)");
        {
            auto p = baseProject();
            p.tracks[1].slots[0] = midiClip ({ { 72, 0.0, 4.0, 1.0f } });
            AudioEngine dry; dry.prepare (SR, BLOCK); load (dry, p); dry.launchClip (1, 0);
            auto a = render (dry, 0.5);
            auto f = makeEffect (EffectType::filter);
            f.params["cutoff"] = 60.0f;
            p.tracks[1].effects.push_back (f);
            AudioEngine wet; wet.prepare (SR, BLOCK); load (wet, p); wet.launchClip (1, 0);
            auto b = render (wet, 0.5);
            expect (rms (b, 0.1, 0.5) < rms (a, 0.1, 0.5) * 0.5f, "low-pass at 60 Hz attenuates a C5 saw");
        }

        beginTest ("All 16 drum pads make sound with the built-in kit");
        {
            for (int pad = 0; pad < DrumSampler::numPads; ++pad)
            {
                auto buf = DrumSampler::synthesizePad (pad, SR);
                expect (buf.getMagnitude (0, 0, buf.getNumSamples()) > 0.05f, "pad " + juce::String (pad));
            }
            auto p = baseProject();
            std::vector<Note> notes;
            for (int pad = 0; pad < 16; ++pad) notes.push_back ({ 36 + pad, pad * 0.25, 0.2, 1.0f });
            p.tracks[0].slots[0] = midiClip (notes);
            AudioEngine e; e.prepare (SR, BLOCK); load (e, p); e.launchClip (0, 0);
            auto out = render (e, 2.0);
            expect (finite (out) && rms (out, 0, 2.0) > 0.01f);
        }

        beginTest ("Metronome clicks on beats");
        {
            auto p = baseProject();
            p.metronome = true;
            AudioEngine e; e.prepare (SR, BLOCK); load (e, p);
            e.play();
            auto out = render (e, 1.2);
            expect (rms (out, 0.0, 0.02) > 0.01f && rms (out, 0.5, 0.52) > 0.01f && rms (out, 0.2, 0.45) < 0.001f);
        }

        beginTest ("Live notes play on a track while the transport is stopped");
        {
            AudioEngine e; e.prepare (SR, BLOCK); load (e, baseProject());
            e.noteOn (1, 60, 0.9f);
            auto out = render (e, 0.3);
            expect (rms (out, 0.05, 0.3) > 0.01f);
            expect (! e.isPlaying());
        }

        beginTest ("Recording into a session slot creates a clip and launches it");
        {
            juce::ScopedJuceInitialiser_GUI init;
            ProjectController ctl;
            auto p = baseProject();
            ctl.replaceProject (p);
            AudioEngine e; e.prepare (SR, BLOCK);
            ctl.setPublisher ([&] (auto snap) { e.setProject (snap); });
            e.recordIntoSlot (1, 2, 4.0);          // transport stopped: starts now, 4 beats
            render (e, 0.05);
            e.noteOn (1, 62, 0.8f);
            render (e, 0.5);                        // beat ~1.1
            e.noteOff (1, 62);
            render (e, 1.6);                        // beat ~4.3: recording finished
            e.pollRecording (ctl);
            const auto& slot = ctl.project().tracks[1].slots[2];
            expect (slot != nullptr, "slot filled");
            if (slot)
            {
                expectEquals ((int) slot->notes.size(), 1);
                expectWithinAbsoluteError (slot->notes[0].start, 0.1, 0.05);
                expectWithinAbsoluteError (slot->notes[0].length, 1.0, 0.05);
                expectWithinAbsoluteError (slot->lengthBeats, 4.0, 1e-9);
            }
            expect (e.runtimeFor (1)->playingSlot.load() == 2, "recorded clip is playing");
            expect (ctl.canUndo());
        }

        beginTest ("Arrangement recording captures MIDI on armed tracks");
        {
            juce::ScopedJuceInitialiser_GUI init;
            ProjectController ctl;
            auto p = baseProject();
            p.tracks[1].arm = true;
            ctl.replaceProject (p);
            AudioEngine e; e.prepare (SR, BLOCK);
            ctl.setPublisher ([&] (auto snap) { e.setProject (snap); });
            juce::String err;
            expect (e.startRecording (err), err);
            render (e, 0.5);                        // beat 1
            e.noteOn (1, 67, 1.0f);
            render (e, 0.5);
            e.noteOff (1, 67);
            render (e, 0.5);
            e.stopRecording (ctl);
            const auto& arr = ctl.project().tracks[1].arrangement;
            expectEquals ((int) arr.size(), 1);
            if (! arr.empty())
            {
                expectEquals ((int) arr[0].clip->notes.size(), 1);
                expectWithinAbsoluteError (arr[0].clip->notes[0].start, 1.0, 0.02);
                expectWithinAbsoluteError (arr[0].clip->notes[0].length, 1.0, 0.03);
            }
        }

        beginTest ("Audio recording writes a WAV and places an audio clip");
        {
            juce::ScopedJuceInitialiser_GUI init;
            ProjectController ctl;
            auto p = baseProject();
            auto audio = makeTrack (TrackKind::audio, "Vox", 2);
            audio.arm = true;
            p.tracks.push_back (audio);
            ctl.replaceProject (p);
            AudioEngine e; e.prepare (SR, BLOCK);
            ctl.setPublisher ([&] (auto snap) { e.setProject (snap); });
            juce::AudioBuffer<float> in (2, (int) (SR * 1.0));
            for (int i = 0; i < in.getNumSamples(); ++i) { in.setSample (0, i, 0.3f); in.setSample (1, i, 0.3f); }
            juce::String err;
            expect (e.startRecording (err), err);
            render (e, 1.0, &in);
            e.stopRecording (ctl);
            const auto& arr = ctl.project().tracks[2].arrangement;
            expectEquals ((int) arr.size(), 1);
            if (! arr.empty())
            {
                juce::File f (arr[0].clip->audioFile);
                expect (f.existsAsFile());
                expectWithinAbsoluteError (AudioFileCache::durationSeconds (f), 1.0, 0.02);
                f.deleteFile();
            }
        }

        beginTest ("Export renders the arrangement to a WAV file");
        {
            auto p = baseProject();
            p.tracks[0].arrangement.push_back ({ midiClip ({ { 36, 0.0, 0.5, 1.0f }, { 38, 1.0, 0.5, 1.0f } }), 0.0, 4.0 });
            p.tracks[1].arrangement.push_back ({ midiClip ({ { 60, 0.0, 2.0, 0.8f } }), 4.0, 4.0 });
            auto f = juce::File::createTempFile (".wav");
            ExportOptions o; o.sampleRate = 44100; o.tailSeconds = 1.0;
            juce::String err;
            std::atomic<double> progress { 0 };
            expect (exportArrangement (std::make_shared<const Project> (p), f, o, err, &progress), err);
            expectWithinAbsoluteError (AudioFileCache::durationSeconds (f), 8 * 0.5 + 1.0, 0.02);
            expectEquals (progress.load(), 1.0);
            juce::AudioFormatManager fm; fm.registerBasicFormats();
            std::unique_ptr<juce::AudioFormatReader> r (fm.createReaderFor (f));
            juce::AudioBuffer<float> b (2, (int) r->lengthInSamples);
            r->read (&b, 0, b.getNumSamples(), 0, true, true);
            expect (b.getMagnitude (0, b.getNumSamples()) > 0.05f, "export not silent");
            Project empty = baseProject();
            expect (! exportArrangement (std::make_shared<const Project> (empty), f, o, err), "empty arrangement refused");
            f.deleteFile();
        }

        beginTest ("Quantize helper");
        {
            expectEquals (AudioEngine::quantizedLaunchBeat (0.5, 4, true), 4.0);
            expectEquals (AudioEngine::quantizedLaunchBeat (4.0, 4, true), 4.0);
            expectEquals (AudioEngine::quantizedLaunchBeat (4.1, 4, true), 8.0);
            expectEquals (AudioEngine::quantizedLaunchBeat (4.1, 0, true), 4.1);
            expectEquals (AudioEngine::quantizedLaunchBeat (3.0, 4, false), 3.0);
        }
    }
};

static EngineTests engineTests;
