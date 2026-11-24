#include "AudioEngine.h"

namespace tessera
{

AudioEngine::AudioEngine()
{
    writerThread.startThread();
}

AudioEngine::~AudioEngine()
{
    {
        const juce::SpinLock::ScopedLockType l (writerLock);
        audioWriter.reset();
    }
    writerThread.stopThread (2000);
}

// ======================================================================== setup

static juce::AudioBuffer<float> makeClick (double sr, double freq)
{
    juce::AudioBuffer<float> b (1, (int) (sr * 0.03));
    for (int i = 0; i < b.getNumSamples(); ++i)
    {
        const double t = i / sr;
        b.setSample (0, i, (float) (0.5 * std::sin (juce::MathConstants<double>::twoPi * freq * t) * std::exp (-t * 120.0)));
    }
    return b;
}

void AudioEngine::prepare (double sampleRate, int maxBlockSize)
{
    sr = sampleRate > 0 ? sampleRate : 44100.0;
    maxBlock = juce::jmax (32, maxBlockSize);
    master.setSize (2, maxBlock);
    clickHi = makeClick (sr, 1500.0);
    clickLo = makeClick (sr, 1000.0);
    for (auto& [id, inst] : instruments) if (inst.second) inst.second->prepare (sr, maxBlock);
    for (auto& [id, fx] : effects) if (fx.second) fx.second->prepare (sr, maxBlock);
    if (latest) setProject (latest->project);   // rebuild buffers / reload audio at the new rate
}

std::shared_ptr<Instrument> AudioEngine::instrumentFor (const Track& t)
{
    auto& slot = instruments[t.id];
    if (slot.second == nullptr || slot.first != t.instrument.type)
    {
        slot.first = t.instrument.type;
        slot.second = std::shared_ptr<Instrument> (createInstrument (t.instrument.type, &cache));
        if (slot.second) slot.second->prepare (sr, maxBlock);
    }
    if (slot.second) slot.second->setParams (t.instrument);
    return slot.second;
}

std::shared_ptr<Effect> AudioEngine::effectFor (const EffectSettings& e)
{
    auto& slot = effects[e.id];
    if (slot.second == nullptr || slot.first != e.type)
    {
        slot.first = e.type;
        slot.second = std::shared_ptr<Effect> (createEffect (e.type));
        slot.second->prepare (sr, maxBlock);
    }
    slot.second->setParams (e);
    return slot.second;
}

void AudioEngine::setProject (std::shared_ptr<const Project> p)
{
    if (p == nullptr) return;
    auto st = std::make_shared<EngineState>();
    st->project = p;
    std::set<juce::String> liveTracks, liveFx;
    for (auto& t : p->tracks)
    {
        liveTracks.insert (t.id);
        TrackDevices d;
        auto& rt = runtimes[t.id];
        if (rt == nullptr) rt = std::make_shared<TrackRuntime>();
        d.runtime = rt;
        d.instrument = t.kind == TrackKind::midi ? instrumentFor (t) : nullptr;
        for (auto& e : t.effects)
        {
            liveFx.insert (e.id);
            auto fx = effectFor (e);
            if (e.enabled) d.effects.push_back (fx);
        }
        d.buffer.setSize (2, maxBlock);
        d.midi.ensureSize (4096);
        auto addAudio = [&] (const ClipPtr& c)
        {
            if (c && c->kind == ClipKind::audio && c->audioFile.isNotEmpty() && ! st->audio.count (c->audioFile))
                st->audio[c->audioFile] = cache.get (c->audioFile, sr);
        };
        for (auto& c : t.slots) addAudio (c);
        for (auto& pl : t.arrangement) addAudio (pl.clip);
        st->tracks.push_back (std::move (d));
    }
    // forget processors of deleted tracks/effects (still referenced by older states until released)
    for (auto it = runtimes.begin(); it != runtimes.end();) it = liveTracks.count (it->first) ? std::next (it) : runtimes.erase (it);
    for (auto it = instruments.begin(); it != instruments.end();) it = liveTracks.count (it->first) ? std::next (it) : instruments.erase (it);
    for (auto it = effects.begin(); it != effects.end();) it = liveFx.count (it->first) ? std::next (it) : effects.erase (it);

    latest = st;
    std::shared_ptr<EngineState> oldPending, oldRetired;
    {
        const juce::SpinLock::ScopedLockType l (stateLock);
        oldPending = std::move (pending);   // never picked up by the audio thread
        oldRetired = std::move (retired);   // handed back by the audio thread
        pending = st;
    }
    // oldPending / oldRetired are destroyed here, on the message thread
}

void AudioEngine::collectGarbage()
{
    std::shared_ptr<EngineState> old;
    const juce::SpinLock::ScopedLockType l (stateLock);
    old = std::move (retired);
}

const TrackRuntime* AudioEngine::runtimeFor (int trackIndex) const
{
    auto st = latest;
    if (st == nullptr || trackIndex < 0 || trackIndex >= (int) st->tracks.size()) return nullptr;
    return st->tracks[(size_t) trackIndex].runtime.get();
}

// ======================================================================== commands

void AudioEngine::push (const Cmd& c)
{
    const juce::SpinLock::ScopedLockType l (cmdWriteLock);   // multiple producer threads are possible (UI + MIDI input)
    auto scope = cmdFifo.write (1);
    if (scope.blockSize1 > 0) cmdBuf[(size_t) scope.startIndex1] = c;
}

void AudioEngine::play() { push ({ Cmd::Play }); }
void AudioEngine::stop() { push ({ Cmd::Stop }); }
void AudioEngine::locate (double beat) { Cmd c { Cmd::Locate }; c.beat = beat; push (c); }
void AudioEngine::launchClip (int track, int slot) { Cmd c { Cmd::Launch }; c.track = track; c.slot = slot; push (c); }
void AudioEngine::stopTrack (int track) { Cmd c { Cmd::StopTrack }; c.track = track; push (c); }
void AudioEngine::launchScene (int slot) { Cmd c { Cmd::LaunchScene }; c.slot = slot; push (c); }
void AudioEngine::stopAllClips() { push ({ Cmd::StopAll }); }
void AudioEngine::noteOn (int track, int note, float v) { Cmd c { Cmd::NoteOn }; c.track = track; c.note = note; c.velocity = v; push (c); }
void AudioEngine::noteOff (int track, int note) { Cmd c { Cmd::NoteOff }; c.track = track; c.note = note; push (c); }
void AudioEngine::recordIntoSlot (int track, int slot, double len) { Cmd c { Cmd::RecordSlot }; c.track = track; c.slot = slot; c.beat = len; push (c); }

double AudioEngine::quantizedLaunchBeat (double now, double quantBeats, bool running)
{
    if (! running || quantBeats <= 0) return now;
    const double q = std::ceil (now / quantBeats - 1e-9) * quantBeats;
    return q;
}

void AudioEngine::pushRec (const RecEvent& e)
{
    auto scope = recFifo.write (1);
    if (scope.blockSize1 > 0) recBuf[(size_t) scope.startIndex1] = e;
}

void AudioEngine::handleCommands (EngineState& st)
{
    const auto& proj = *st.project;
    const double qBeats = proj.launchQuantizeBars * (double) proj.beatsPerBar;
    const int n = cmdFifo.getNumReady();
    if (n == 0) return;
    auto scope = cmdFifo.read (n);
    auto handle = [&] (const Cmd& c)
    {
        auto validTrack = [&] (int t) { return t >= 0 && t < (int) st.tracks.size(); };
        const double now = position.load();
        switch (c.type)
        {
            case Cmd::Play:
                playing = true;
                break;
            case Cmd::Stop:
                if (! playing.load())
                    position = proj.loopEnabled ? proj.loopStart : 0.0;   // second stop returns to start
                playing = false;
                for (auto& d : st.tracks)
                {
                    d.runtime->playingSlot = -1; d.runtime->queuedSlot = -1; d.runtime->stopQueued = false;
                    d.runtime->recordingSlot = -1;
                    d.runtime->panicPending = true;
                }
                break;
            case Cmd::Locate:
                position = juce::jmax (0.0, c.beat);
                for (auto& d : st.tracks) d.runtime->panicPending = true;
                break;
            case Cmd::Launch:
            case Cmd::LaunchAligned:
                if (validTrack (c.track))
                {
                    auto& rt = *st.tracks[(size_t) c.track].runtime;
                    const auto& t = proj.tracks[(size_t) c.track];
                    if (c.slot < 0 || c.slot >= (int) t.slots.size() || t.slots[(size_t) c.slot] == nullptr)
                    {   // launching an empty slot stops the track (like a stop button)
                        rt.stopAtBeat = quantizedLaunchBeat (now, qBeats, playing.load());
                        rt.stopQueued = true;
                        rt.queuedSlot = -1;
                        break;
                    }
                    const bool wasPlaying = playing.load();
                    rt.queuedSlot = c.slot;
                    rt.stopQueued = false;
                    rt.launchAtBeat = c.type == Cmd::LaunchAligned ? c.beat : quantizedLaunchBeat (now, qBeats, wasPlaying);
                    if (! wasPlaying) playing = true;   // launching a clip starts the transport
                }
                break;
            case Cmd::LaunchScene:
            {
                const bool wasPlaying = playing.load();
                const double at = quantizedLaunchBeat (now, qBeats, wasPlaying);
                for (size_t ti = 0; ti < st.tracks.size(); ++ti)
                {
                    auto& rt = *st.tracks[ti].runtime;
                    const auto& t = proj.tracks[ti];
                    if (c.slot >= 0 && c.slot < (int) t.slots.size() && t.slots[(size_t) c.slot] != nullptr)
                    { rt.queuedSlot = c.slot; rt.launchAtBeat = at; rt.stopQueued = false; }
                    else if (rt.playingSlot.load() >= 0)
                    { rt.stopQueued = true; rt.stopAtBeat = at; rt.queuedSlot = -1; }
                }
                if (! wasPlaying) playing = true;
                break;
            }
            case Cmd::StopTrack:
                if (validTrack (c.track))
                {
                    auto& rt = *st.tracks[(size_t) c.track].runtime;
                    rt.queuedSlot = -1;
                    rt.stopQueued = true;
                    rt.stopAtBeat = quantizedLaunchBeat (now, qBeats, playing.load());
                }
                break;
            case Cmd::StopAll:
                for (auto& d : st.tracks)
                {
                    d.runtime->queuedSlot = -1;
                    if (d.runtime->playingSlot.load() >= 0)
                    { d.runtime->stopQueued = true; d.runtime->stopAtBeat = quantizedLaunchBeat (now, qBeats, playing.load()); }
                }
                break;
            case Cmd::NoteOn:
            case Cmd::NoteOff:
                if (validTrack (c.track))
                {
                    auto& d = st.tracks[(size_t) c.track];
                    if (c.type == Cmd::NoteOn) d.midi.addEvent (juce::MidiMessage::noteOn (1, c.note, juce::jlimit (0.01f, 1.0f, c.velocity)), 0);
                    else d.midi.addEvent (juce::MidiMessage::noteOff (1, c.note), 0);
                    auto& rt = *d.runtime;
                    const bool on = c.type == Cmd::NoteOn;
                    if (recording.load() && playing.load() && proj.tracks[(size_t) c.track].arm)
                        pushRec ({ on ? RecEvent::On : RecEvent::Off, c.track, -1, c.note, c.velocity, now });
                    const int rs = rt.recordingSlot.load();
                    if (rs >= 0 && playing.load() && now >= rt.recStartBeat && now < rt.recEndBeat)
                        pushRec ({ on ? RecEvent::On : RecEvent::Off, c.track, rs, c.note, c.velocity, now - rt.recStartBeat });
                }
                break;
            case Cmd::RecordSlot:
                if (validTrack (c.track))
                {
                    auto& rt = *st.tracks[(size_t) c.track].runtime;
                    const bool wasPlaying = playing.load();
                    const double barBeats = (double) proj.beatsPerBar;
                    rt.recStartBeat = quantizedLaunchBeat (now, juce::jmax (barBeats, qBeats), wasPlaying);
                    rt.recEndBeat = rt.recStartBeat + juce::jmax (1.0, c.beat);
                    rt.recordingSlot = c.slot;
                    if (rt.playingSlot.load() >= 0) { rt.stopQueued = true; rt.stopAtBeat = rt.recStartBeat; }
                    if (! wasPlaying) playing = true;
                }
                break;
        }
    };
    for (int i = 0; i < scope.blockSize1; ++i) handle (cmdBuf[(size_t) (scope.startIndex1 + i)]);
    for (int i = 0; i < scope.blockSize2; ++i) handle (cmdBuf[(size_t) (scope.startIndex2 + i)]);
}

// ======================================================================== rendering

void AudioEngine::allOff (TrackRuntime& rt, juce::MidiBuffer& midi, int sample)
{
    for (int n = 0; n < 128; ++n)
        if (rt.sounding[(size_t) n]) { midi.addEvent (juce::MidiMessage::noteOff (1, n), sample); rt.sounding[(size_t) n] = false; }
}

void AudioEngine::emitMidiClip (TrackRuntime& rt, juce::MidiBuffer& midi, const Clip& clip, double clipStart, bool loop,
                                double r0, double r1, double b0, int offset, int len, double bps, double hardEnd)
{
    const double L = juce::jmax (0.0625, clip.lengthBeats);
    auto toSample = [&] (double beat) { return juce::jlimit (offset, offset + len - 1, offset + (int) std::floor ((beat - b0) / bps)); };
    const double rel0 = r0 - clipStart, rel1 = r1 - clipStart;
    const int k0 = loop ? (int) std::floor (rel0 / L) : 0;
    const int k1 = loop ? (int) std::floor (rel1 / L) : 0;
    for (int k = juce::jmax (0, k0); k <= k1; ++k)
    {
        const double iter = clipStart + k * L;
        for (auto& n : clip.notes)
        {
            if (n.start >= L) continue;
            const double on = iter + n.start;
            const double off = juce::jmin (iter + juce::jmin (n.start + n.length, L), hardEnd);
            if (off <= on) continue;
            const bool onHere = on >= r0 && on < r1;
            const bool offHere = off > r0 && off <= r1;
            auto& snd = rt.sounding[(size_t) n.pitch];
            if (onHere)
            {
                if (snd) midi.addEvent (juce::MidiMessage::noteOff (1, n.pitch), toSample (on));
                midi.addEvent (juce::MidiMessage::noteOn (1, n.pitch, juce::jlimit (0.01f, 1.0f, n.velocity)), toSample (on));
                snd = true;
            }
            if (offHere && (onHere || on < r0) && snd)
            {
                midi.addEvent (juce::MidiMessage::noteOff (1, n.pitch), juce::jmax (toSample (off), toSample (on)));
                snd = false;
            }
        }
        if (! loop) break;
    }
    if (r1 >= hardEnd - 1e-9) allOff (rt, midi, toSample (hardEnd));
}

void AudioEngine::emitAudioClip (const EngineState& st, juce::AudioBuffer<float>& buf, const Clip& clip, double clipStart, bool loop,
                                 double r0, double r1, double b0, int offset, int len, double bps, double tempo)
{
    auto it = st.audio.find (clip.audioFile);
    if (it == st.audio.end() || it->second == nullptr) return;
    const auto& src = *it->second;
    const int srcLen = src.getNumSamples();
    const double L = juce::jmax (0.0625, clip.lengthBeats);
    const float g = juce::Decibels::decibelsToGain (clip.gainDb);
    const int s0 = juce::jlimit (offset, offset + len, offset + (int) std::ceil ((r0 - b0) / bps - 1e-9));
    const int s1 = juce::jlimit (offset, offset + len, offset + (int) std::ceil ((r1 - b0) / bps - 1e-9));
    // seconds of source audio per clip beat
    const double secPerBeat = clip.warp ? 60.0 / juce::jmax (1.0, clip.sourceTempo) : 60.0 / juce::jmax (1.0, tempo);
    for (int i = s0; i < s1; ++i)
    {
        double local = b0 + (i - offset) * bps - clipStart;
        if (loop) local = std::fmod (local, L);
        if (local < 0 || local >= L) continue;
        const double srcPos = local * secPerBeat * sr;
        const int idx = (int) srcPos;
        if (idx < 0 || idx >= srcLen - 1) continue;
        const float fr = (float) (srcPos - idx);
        for (int c = 0; c < 2; ++c)
            buf.getWritePointer (c)[i] += g * (src.getSample (c, idx) * (1 - fr) + src.getSample (c, idx + 1) * fr);
    }
}

void AudioEngine::renderTrackRange (EngineState& st, int ti, double b0, double b1, int offset, int len, double bps, bool moving)
{
    auto& d = st.tracks[(size_t) ti];
    auto& rt = *d.runtime;
    const auto& t = st.project->tracks[(size_t) ti];
    const double tempo = st.project->tempo;
    auto toSample = [&] (double beat) { return juce::jlimit (offset, offset + len - 1, offset + (int) std::floor ((beat - b0) / bps)); };

    if (rt.panicPending) { allOff (rt, d.midi, offset); rt.panicPending = false; }
    if (! moving) return;

    // Split [b0,b1) at queued launch/stop/record boundaries so switches are sample-accurate.
    double cur = b0;
    auto renderSource = [&] (double r0, double r1)
    {
        if (r1 <= r0) return;
        const int slot = rt.playingSlot.load();
        if (slot >= 0 && slot < (int) t.slots.size() && t.slots[(size_t) slot])
        {
            const auto& clip = *t.slots[(size_t) slot];
            if (clip.kind == ClipKind::midi) emitMidiClip (rt, d.midi, clip, rt.clipStartBeat, true, r0, r1, b0, offset, len, bps, 1e12);
            else emitAudioClip (st, d.buffer, clip, rt.clipStartBeat, true, r0, r1, b0, offset, len, bps, tempo);
            rt.clipPhase = std::fmod (juce::jmax (0.0, r1 - rt.clipStartBeat), clip.lengthBeats) / clip.lengthBeats;
            return;
        }
        if (slot >= 0) return;   // playing slot was emptied: silence until stopped
        for (auto& pl : t.arrangement)   // arrangement plays when no session clip is active on this track
        {
            const double ps = pl.startBeat, pe = pl.startBeat + pl.lengthBeats;
            const double a = juce::jmax (r0, ps), b = juce::jmin (r1, pe);
            if (b <= a) continue;
            const bool loop = pl.clip->looping || pl.lengthBeats <= pl.clip->lengthBeats + 1e-9;
            if (pl.clip->kind == ClipKind::midi) emitMidiClip (rt, d.midi, *pl.clip, ps, loop, a, b, b0, offset, len, bps, pe);
            else emitAudioClip (st, d.buffer, *pl.clip, ps, loop, a, b, b0, offset, len, bps, tempo);
        }
    };

    const int q = rt.queuedSlot.load();
    if (q >= 0 && rt.launchAtBeat < b1 - 1e-12)
    {
        const double at = juce::jmax (cur, rt.launchAtBeat);
        renderSource (cur, at);
        allOff (rt, d.midi, toSample (at));
        rt.playingSlot = q;
        rt.queuedSlot = -1;
        rt.clipStartBeat = rt.launchAtBeat;
        cur = at;
    }
    if (rt.stopQueued.load() && rt.stopAtBeat < b1 - 1e-12)
    {
        const double at = juce::jmax (cur, rt.stopAtBeat);
        renderSource (cur, at);
        allOff (rt, d.midi, toSample (at));
        rt.playingSlot = -1;
        rt.stopQueued = false;
        cur = at;
    }
    const int rs = rt.recordingSlot.load();
    if (rs >= 0 && rt.recEndBeat < b1 - 1e-12 && rt.recEndBeat >= b0)
    {   // slot recording finished: launch the new clip aligned with its recording start
        renderSource (cur, rt.recEndBeat);
        pushRec ({ RecEvent::SlotDone, ti, rs, 0, 0, rt.recEndBeat - rt.recStartBeat });
        rt.recordingSlot = -1;
        rt.playingSlot = rs;
        rt.clipStartBeat = rt.recEndBeat;
        cur = rt.recEndBeat;
    }
    renderSource (cur, b1);
}

void AudioEngine::renderBlock (float* const* outputs, int numOutputs, const float* const* inputs, int numInputs, int numSamples)
{
    {
        const juce::SpinLock::ScopedTryLockType l (stateLock);
        if (l.isLocked() && pending != nullptr && retired == nullptr)
        {
            retired = std::move (active);   // freed later on the message thread, never here
            active = std::move (pending);
        }
    }
    for (int c = 0; c < numOutputs; ++c) if (outputs[c]) juce::FloatVectorOperations::clear (outputs[c], numSamples);
    if (active == nullptr) return;
    auto& st = *active;
    const auto& proj = *st.project;

    int done = 0;
    while (done < numSamples)
    {
        const int n = juce::jmin (maxBlock, numSamples - done);
        handleCommands (st);
        for (auto& d : st.tracks) { d.buffer.clear (0, n); }
        master.clear (0, n);

        const bool moving = playing.load();
        const double bps = proj.tempo / (60.0 * sr);   // beats per sample
        double pos = position.load();

        // segments (loop wrap)
        struct Seg { int offset, len; double b0; };
        std::array<Seg, 2> segs {};
        int numSegs = 1;
        segs[0] = { 0, n, pos };
        double endPos = pos + n * bps;
        if (moving && proj.loopEnabled && proj.loopEnd > proj.loopStart && pos < proj.loopEnd && endPos > proj.loopEnd)
        {
            const int k = juce::jlimit (1, n - 1, (int) std::ceil ((proj.loopEnd - pos) / bps));
            segs[0] = { 0, k, pos };
            segs[1] = { k, n - k, proj.loopStart };
            numSegs = 2;
            endPos = proj.loopStart + (n - k) * bps;
        }

        for (int s = 0; s < numSegs; ++s)
        {
            const auto& sg = segs[(size_t) s];
            const double b1 = sg.b0 + sg.len * bps;
            if (s == 1) for (auto& d : st.tracks) allOff (*d.runtime, d.midi, sg.offset);
            for (int ti = 0; ti < (int) st.tracks.size(); ++ti)
                renderTrackRange (st, ti, sg.b0, b1, sg.offset, sg.len, bps, moving);
            if (moving && proj.metronome)
            {
                const double firstBeat = std::ceil (sg.b0 - 1e-9);
                for (double beat = firstBeat; beat < b1; beat += 1.0)
                {
                    clickIdx = 0;
                    clickDelay = sg.offset + (int) ((beat - sg.b0) / bps);
                    clickAccent = ((int) std::llround (beat)) % juce::jmax (1, proj.beatsPerBar) == 0;
                }
            }
        }

        // audio recording (first armed audio track, from inputs 1-2)
        if (moving && recording.load() && numInputs > 0)
        {
            const juce::SpinLock::ScopedTryLockType wl (writerLock);
            if (wl.isLocked() && audioWriter)
            {
                const float* ins[2] = { inputs[0] ? inputs[0] + done : nullptr,
                                        numInputs > 1 && inputs[1] ? inputs[1] + done : (inputs[0] ? inputs[0] + done : nullptr) };
                if (ins[0]) audioWriter->write (ins, n);
            }
        }

        // instruments, effects, mixer
        bool anySolo = false;
        for (auto& t : proj.tracks) anySolo = anySolo || t.solo;
        for (size_t ti = 0; ti < st.tracks.size(); ++ti)
        {
            auto& d = st.tracks[ti];
            const auto& t = proj.tracks[ti];
            if (d.instrument) d.instrument->process (d.buffer, d.midi, n);
            d.midi.clear();
            for (auto& fx : d.effects) fx->process (d.buffer, n, proj.tempo);
            const bool audible = ! t.mute && (! anySolo || t.solo);
            const float g = audible ? juce::Decibels::decibelsToGain (t.volumeDb, -80.0f) : 0.0f;
            const float panAngle = (t.pan + 1.0f) * juce::MathConstants<float>::pi * 0.25f;
            const float gl = g * std::cos (panAngle) * juce::MathConstants<float>::sqrt2;
            const float gr = g * std::sin (panAngle) * juce::MathConstants<float>::sqrt2;
            d.buffer.applyGain (0, 0, n, gl);
            d.buffer.applyGain (1, 0, n, gr);
            d.runtime->peakL = juce::jmax (d.runtime->peakL.load() * 0.9f, d.buffer.getMagnitude (0, 0, n));
            d.runtime->peakR = juce::jmax (d.runtime->peakR.load() * 0.9f, d.buffer.getMagnitude (1, 0, n));
            master.addFrom (0, 0, d.buffer, 0, 0, n);
            master.addFrom (1, 0, d.buffer, 1, 0, n);
        }

        // metronome
        if (clickIdx >= 0)
        {
            const auto& click = clickAccent ? clickHi : clickLo;
            for (int i = clickDelay; i < n && clickIdx < click.getNumSamples(); ++i, ++clickIdx)
            {
                master.addSample (0, i, click.getSample (0, clickIdx));
                master.addSample (1, i, click.getSample (0, clickIdx));
            }
            clickDelay = 0;
            if (clickIdx >= click.getNumSamples()) clickIdx = -1;
        }

        master.applyGain (0, n, juce::Decibels::decibelsToGain (proj.masterVolumeDb, -80.0f));
        masterL = juce::jmax (masterL.load() * 0.9f, master.getMagnitude (0, 0, n));
        masterR = juce::jmax (masterR.load() * 0.9f, master.getMagnitude (1, 0, n));
        for (int c = 0; c < numOutputs; ++c)
            if (outputs[c]) juce::FloatVectorOperations::copy (outputs[c] + done, master.getReadPointer (juce::jmin (c, 1)), n);

        if (moving) position = endPos;
        done += n;
    }
}

void AudioEngine::audioDeviceIOCallbackWithContext (const float* const* in, int numIn, float* const* out, int numOut, int numSamples,
                                                    const juce::AudioIODeviceCallbackContext&)
{
    juce::ScopedNoDenormals noDenormals;
    renderBlock (out, numOut, in, numIn, numSamples);
}

void AudioEngine::audioDeviceAboutToStart (juce::AudioIODevice* device)
{
    const double rate = device->getCurrentSampleRate();
    const int block = device->getCurrentBufferSizeSamples();
    if (juce::MessageManager::getInstanceWithoutCreating() != nullptr && ! juce::MessageManager::getInstance()->isThisTheMessageThread())
    {
        // Rebuilding processors must happen on the message thread; render silence until then.
        juce::MessageManager::callAsync ([this, rate, block] { prepare (rate, block); });
        return;
    }
    prepare (rate, block);
}

// ======================================================================== recording

bool AudioEngine::startRecording (juce::String& error)
{
    auto st = latest;
    if (st == nullptr) return false;
    recordStartBeat = position.load();
    recordedNotes.clear();
    openNotes.clear();
    recordingAudioTrack = -1;
    for (size_t i = 0; i < st->project->tracks.size(); ++i)
        if (st->project->tracks[i].arm && st->project->tracks[i].kind == TrackKind::audio) { recordingAudioTrack = (int) i; break; }
    if (recordingAudioTrack >= 0)
    {
        auto dir = juce::File::getSpecialLocation (juce::File::userMusicDirectory).getChildFile ("Tessera Recordings");
        dir.createDirectory();
        recordingFile = dir.getNonexistentChildFile ("Recording-" + juce::Time::getCurrentTime().formatted ("%Y%m%d-%H%M%S"), ".wav");
        std::unique_ptr<juce::OutputStream> os (recordingFile.createOutputStream());
        juce::WavAudioFormat wav;
        std::unique_ptr<juce::AudioFormatWriter> w;
        if (os) w.reset (wav.createWriterFor (os.get(), sr, 2, 24, {}, 0));
        if (w == nullptr) { error = "Could not create " + recordingFile.getFullPathName(); return false; }
        os.release();
        const juce::SpinLock::ScopedLockType l (writerLock);
        audioWriter = std::make_unique<juce::AudioFormatWriter::ThreadedWriter> (w.release(), writerThread, (int) (sr * 8));
    }
    recording = true;
    play();
    return true;
}

void AudioEngine::pollRecording (ProjectController& controller)
{
    collectGarbage();
    const int n = recFifo.getNumReady();
    if (n == 0) return;
    auto scope = recFifo.read (n);
    std::vector<RecEvent> evs;
    for (int i = 0; i < scope.blockSize1; ++i) evs.push_back (recBuf[(size_t) (scope.startIndex1 + i)]);
    for (int i = 0; i < scope.blockSize2; ++i) evs.push_back (recBuf[(size_t) (scope.startIndex2 + i)]);
    for (auto& e : evs)
    {
        if (e.type == RecEvent::SlotDone)
        {
            auto key = std::make_pair (e.track, e.slot);
            auto notes = slotNotes[key];
            slotNotes.erase (key);
            const auto& proj = controller.project();
            if (e.track < 0 || e.track >= (int) proj.tracks.size()) continue;
            auto clip = std::make_shared<Clip>();
            clip->id = Clip::newId();
            clip->name = "Recorded";
            clip->kind = ClipKind::midi;
            clip->colour = proj.tracks[(size_t) e.track].colour;
            clip->lengthBeats = e.beat;
            for (auto& nt : notes) if (nt.start < e.beat) clip->notes.push_back (nt);
            std::sort (clip->notes.begin(), clip->notes.end(), [] (auto& a, auto& b) { return a.start < b.start; });
            const int ti = e.track, si = e.slot;
            controller.edit ("Record clip", [ti, si, clip] (Project& p)
            {
                p.ensureSlotCount();
                if (ti < (int) p.tracks.size() && si < (int) p.tracks[(size_t) ti].slots.size()) p.tracks[(size_t) ti].slots[(size_t) si] = clip;
            });
            continue;
        }
        const bool slot = e.slot >= 0;
        auto key = std::make_pair (e.track * 1000 + (slot ? e.slot + 1 : 0), e.note);
        if (e.type == RecEvent::On) openNotes[key] = { e.beat, e.velocity };
        else if (auto it = openNotes.find (key); it != openNotes.end())
        {
            Note nt { e.note, it->second.first, juce::jmax (0.01, e.beat - it->second.first), it->second.second };
            if (slot) slotNotes[{ e.track, e.slot }].push_back (nt);
            else recordedNotes[e.track].push_back (nt);
            openNotes.erase (it);
        }
    }
}

void AudioEngine::stopRecording (ProjectController& controller)
{
    if (! recording.exchange (false)) return;
    pollRecording (controller);
    const double endBeat = position.load();
    {
        const juce::SpinLock::ScopedLockType l (writerLock);
        audioWriter.reset();   // flushes and closes the file
    }
    Project p = controller.project();
    bool changed = false;
    // close notes still held at stop
    for (auto& [key, v] : openNotes)
        if (key.first < 1000 * 1000 && key.first % 1000 == 0)
            recordedNotes[key.first / 1000].push_back ({ key.second, v.first, juce::jmax (0.01, endBeat - v.first), v.second });
    openNotes.clear();
    const double length = juce::jmax (1.0, std::ceil ((endBeat - recordStartBeat) / p.beatsPerBar) * p.beatsPerBar);
    for (auto& [ti, notes] : recordedNotes)
    {
        if (ti < 0 || ti >= (int) p.tracks.size() || notes.empty()) continue;
        auto clip = std::make_shared<Clip>();
        clip->id = Clip::newId();
        clip->name = "Take";
        clip->colour = p.tracks[(size_t) ti].colour;
        clip->lengthBeats = length;
        clip->looping = false;
        for (auto n : notes) { n.start -= recordStartBeat; if (n.start >= 0) clip->notes.push_back (n); }
        std::sort (clip->notes.begin(), clip->notes.end(), [] (auto& a, auto& b) { return a.start < b.start; });
        p.tracks[(size_t) ti].arrangement.push_back ({ clip, recordStartBeat, length });
        changed = true;
    }
    recordedNotes.clear();
    if (recordingAudioTrack >= 0 && recordingAudioTrack < (int) p.tracks.size() && recordingFile.existsAsFile())
    {
        auto clip = std::make_shared<Clip>();
        clip->id = Clip::newId();
        clip->name = recordingFile.getFileNameWithoutExtension();
        clip->kind = ClipKind::audio;
        clip->audioFile = recordingFile.getFullPathName();
        clip->colour = p.tracks[(size_t) recordingAudioTrack].colour;
        clip->sourceTempo = p.tempo;
        clip->lengthBeats = juce::jmax (0.25, endBeat - recordStartBeat);
        clip->looping = false;
        p.tracks[(size_t) recordingAudioTrack].arrangement.push_back ({ clip, recordStartBeat, clip->lengthBeats });
        changed = true;
    }
    recordingAudioTrack = -1;
    if (changed) controller.replaceProject (std::move (p));
}

} // namespace tessera
