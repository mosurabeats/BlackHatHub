#include "Project.h"
#include "Params.h"

namespace tessera
{

juce::String Clip::newId() { return juce::Uuid().toString().substring (0, 12); }

juce::Colour paletteColour (int index)
{
    static const juce::uint32 cols[] = { 0xff4fb0a5, 0xffe0a43a, 0xff7a8cff, 0xffe06c8a, 0xff8cc84b,
                                         0xffc58af0, 0xff4c9be8, 0xffe07a4a, 0xff5fd0c0, 0xffd8c84a };
    return juce::Colour (cols[(size_t) std::abs (index) % std::size (cols)]);
}

juce::String effectTypeName (EffectType t)
{
    switch (t)
    {
        case EffectType::eq3: return "EQ Three";
        case EffectType::compressor: return "Compressor";
        case EffectType::delay: return "Delay";
        case EffectType::reverb: return "Reverb";
        case EffectType::filter: return "Filter";
    }
    return "Effect";
}

EffectSettings makeEffect (EffectType type)
{
    EffectSettings e;
    e.id = Clip::newId();
    e.type = type;
    e.params = defaultsFor (effectParams (type));
    return e;
}

Track makeTrack (TrackKind kind, const juce::String& name, int index)
{
    Track t;
    t.id = Clip::newId();
    t.name = name;
    t.kind = kind;
    t.colour = paletteColour (index);
    if (kind == TrackKind::midi)
    {
        t.instrument.type = InstrumentType::synth;
        t.instrument.params = defaultsFor (synthParams());
    }
    else
    {
        t.instrument.type = InstrumentType::none;
    }
    return t;
}

Project Project::createDefault()
{
    Project p;
    for (int i = 0; i < 8; ++i) p.scenes.push_back ({ juce::String (i + 1) });
    auto drums = makeTrack (TrackKind::midi, "Drums", 0);
    drums.instrument.type = InstrumentType::drums;
    drums.instrument.params = defaultsFor (drumParams());
    p.tracks.push_back (drums);
    p.tracks.push_back (makeTrack (TrackKind::midi, "Synth", 1));
    p.tracks.push_back (makeTrack (TrackKind::audio, "Audio", 2));
    p.ensureSlotCount();
    return p;
}

Project Project::createDemo()
{
    Project p = createDefault();
    p.tempo = 118.0;
    p.scenes = { { "Intro" }, { "Groove" }, { "Lift" }, { "Break" }, { "5" }, { "6" }, { "7" }, { "8" } };
    p.ensureSlotCount();
    auto clip = [] (const juce::String& name, juce::Colour c, double len, std::vector<Note> notes)
    {
        auto cl = std::make_shared<Clip>();
        cl->id = Clip::newId();
        cl->name = name;
        cl->colour = c;
        cl->lengthBeats = len;
        cl->notes = std::move (notes);
        std::sort (cl->notes.begin(), cl->notes.end(), [] (auto& a, auto& b) { return a.start < b.start; });
        return std::shared_ptr<const Clip> (cl);
    };
    // drums: 36 kick, 38 snare, 42 closed hat, 46 open hat, 39 clap
    std::vector<Note> hats, beat, beatFull, brk;
    for (int i = 0; i < 16; ++i) hats.push_back ({ 42, i * 0.5, 0.25, i % 2 ? 0.55f : 0.8f });
    beat = hats;
    for (double b : { 0.0, 1.5, 2.0, 4.0, 5.5, 6.0 }) beat.push_back ({ 36, b, 0.5, 1.0f });
    for (double b : { 1.0, 3.0, 5.0, 7.0 }) beat.push_back ({ 38, b, 0.5, 0.9f });
    beatFull = beat;
    beatFull.push_back ({ 46, 7.5, 0.5, 0.8f });
    for (double b : { 1.0, 3.0, 5.0, 7.0 }) beatFull.push_back ({ 39, b, 0.5, 0.6f });
    for (double b : { 0.0, 2.5, 4.0, 6.75 }) brk.push_back ({ 36, b, 0.5, 0.9f });
    brk.push_back ({ 38, 3.0, 0.5, 0.8f });
    brk.push_back ({ 38, 7.0, 0.5, 0.8f });
    auto& d = p.tracks[0];
    d.slots[0] = clip ("Hats", d.colour, 8, hats);
    d.slots[1] = clip ("Beat", d.colour, 8, beat);
    d.slots[2] = clip ("Beat+", d.colour, 8, beatFull);
    d.slots[3] = clip ("Break", d.colour, 8, brk);
    // synth: bass line and chords in A minor (A - F - C - G)
    auto& s = p.tracks[1];
    s.name = "Bass";
    s.instrument.params["cutoff"] = 700.0f;
    s.instrument.params["osc2Detune"] = -12.0f;
    s.instrument.params["release"] = 0.15f;
    std::vector<Note> bass;
    const int roots[] = { 45, 41, 48, 43 };
    for (int bar = 0; bar < 4; ++bar)
        for (double b : { 0.0, 0.75, 1.5, 2.5, 3.0 }) bass.push_back ({ roots[bar] - 12, bar * 4 + b, 0.5, b == 0 ? 1.0f : 0.75f });
    s.slots[1] = clip ("Bassline", s.colour, 16, bass);
    s.slots[2] = s.slots[1];
    auto keys = makeTrack (TrackKind::midi, "Keys", 3);
    keys.instrument.params["attack"] = 0.08f;
    keys.instrument.params["release"] = 1.2f;
    keys.instrument.params["cutoff"] = 2400.0f;
    keys.effects.push_back (makeEffect (EffectType::reverb));
    keys.effects.push_back (makeEffect (EffectType::delay));
    keys.slots.resize (p.scenes.size());
    std::vector<Note> chords;
    const int chordNotes[4][3] = { { 57, 60, 64 }, { 53, 57, 60 }, { 55, 60, 64 }, { 55, 59, 62 } };
    for (int bar = 0; bar < 4; ++bar)
        for (int n : chordNotes[bar]) chords.push_back ({ n, bar * 4.0, 3.5, 0.6f });
    keys.slots[0] = clip ("Pads", keys.colour, 16, chords);
    keys.slots[2] = keys.slots[0];
    keys.slots[3] = keys.slots[0];
    p.tracks.insert (p.tracks.begin() + 2, keys);
    // a short arrangement built from the scenes
    auto place = [&] (int track, int slot, double at, double len)
    { p.tracks[(size_t) track].arrangement.push_back ({ p.tracks[(size_t) track].slots[(size_t) slot], at, len }); };
    place (0, 0, 0, 16);  place (2, 0, 0, 16);
    place (0, 1, 16, 16); place (1, 1, 16, 16);
    place (0, 2, 32, 16); place (1, 2, 32, 16); place (2, 2, 32, 16);
    place (0, 3, 48, 8);  place (2, 3, 48, 16);
    p.loopStart = 16; p.loopEnd = 32;
    p.ensureSlotCount();
    return p;
}

void Project::ensureSlotCount()
{
    for (auto& t : tracks) t.slots.resize (scenes.size());
}

Track* Project::findTrack (const juce::String& id)
{
    for (auto& t : tracks) if (t.id == id) return &t;
    return nullptr;
}

const Track* Project::findTrack (const juce::String& id) const
{
    for (auto& t : tracks) if (t.id == id) return &t;
    return nullptr;
}

int Project::trackIndex (const juce::String& id) const
{
    for (size_t i = 0; i < tracks.size(); ++i) if (tracks[i].id == id) return (int) i;
    return -1;
}

double Project::arrangementEndBeat() const
{
    double end = 0.0;
    for (auto& t : tracks)
        for (auto& pl : t.arrangement) end = std::max (end, pl.startBeat + pl.lengthBeats);
    return end;
}

// ------------------------------------------------------------------ serialization

static juce::var paramsToVar (const std::map<juce::String, float>& m)
{
    auto* o = new juce::DynamicObject();
    for (auto& [k, v] : m) o->setProperty (k, v);
    return juce::var (o);
}

static std::map<juce::String, float> paramsFromVar (const juce::var& v)
{
    std::map<juce::String, float> m;
    if (auto* o = v.getDynamicObject())
        for (auto& p : o->getProperties()) m[p.name.toString()] = (float) (double) p.value;
    return m;
}

static juce::var clipToVar (const Clip& c)
{
    auto* o = new juce::DynamicObject();
    o->setProperty ("id", c.id);
    o->setProperty ("name", c.name);
    o->setProperty ("kind", c.kind == ClipKind::midi ? "midi" : "audio");
    o->setProperty ("colour", c.colour.toString());
    o->setProperty ("length", c.lengthBeats);
    o->setProperty ("looping", c.looping);
    juce::Array<juce::var> notes;
    for (auto& n : c.notes)
        notes.add (juce::Array<juce::var> { n.pitch, n.start, n.length, n.velocity });
    o->setProperty ("notes", notes);
    o->setProperty ("audioFile", c.audioFile);
    o->setProperty ("sourceTempo", c.sourceTempo);
    o->setProperty ("warp", c.warp);
    o->setProperty ("gainDb", c.gainDb);
    return juce::var (o);
}

static ClipPtr clipFromVar (const juce::var& v)
{
    if (! v.isObject()) return nullptr;
    auto c = std::make_shared<Clip>();
    c->id = v.getProperty ("id", Clip::newId()).toString();
    c->name = v.getProperty ("name", "Clip").toString();
    c->kind = v.getProperty ("kind", "midi").toString() == "audio" ? ClipKind::audio : ClipKind::midi;
    c->colour = juce::Colour::fromString (v.getProperty ("colour", "ff4fb0a5").toString());
    c->lengthBeats = juce::jmax (0.0625, (double) v.getProperty ("length", 4.0));
    c->looping = v.getProperty ("looping", true);
    if (auto* arr = v.getProperty ("notes", {}).getArray())
        for (auto& n : *arr)
            if (auto* a = n.getArray(); a != nullptr && a->size() == 4)
                c->notes.push_back ({ juce::jlimit (0, 127, (int) (*a)[0]), (double) (*a)[1],
                                      juce::jmax (0.001, (double) (*a)[2]), juce::jlimit (0.0f, 1.0f, (float) (double) (*a)[3]) });
    std::sort (c->notes.begin(), c->notes.end(), [] (auto& a, auto& b) { return a.start < b.start; });
    c->audioFile = v.getProperty ("audioFile", "").toString();
    c->sourceTempo = v.getProperty ("sourceTempo", 120.0);
    c->warp = v.getProperty ("warp", true);
    c->gainDb = (float) (double) v.getProperty ("gainDb", 0.0);
    return c;
}

juce::var Project::toVar() const
{
    auto* o = new juce::DynamicObject();
    o->setProperty ("format", "tessera-project");
    o->setProperty ("version", 1);
    o->setProperty ("tempo", tempo);
    o->setProperty ("beatsPerBar", beatsPerBar);
    o->setProperty ("launchQuantizeBars", launchQuantizeBars);
    o->setProperty ("masterVolumeDb", masterVolumeDb);
    o->setProperty ("metronome", metronome);
    o->setProperty ("loopStart", loopStart);
    o->setProperty ("loopEnd", loopEnd);
    o->setProperty ("loopEnabled", loopEnabled);
    juce::Array<juce::var> sc;
    for (auto& s : scenes) sc.add (s.name);
    o->setProperty ("scenes", sc);
    juce::Array<juce::var> tr;
    for (auto& t : tracks)
    {
        auto* to = new juce::DynamicObject();
        to->setProperty ("id", t.id);
        to->setProperty ("name", t.name);
        to->setProperty ("kind", t.kind == TrackKind::midi ? "midi" : "audio");
        to->setProperty ("colour", t.colour.toString());
        to->setProperty ("volumeDb", t.volumeDb);
        to->setProperty ("pan", t.pan);
        to->setProperty ("mute", t.mute);
        to->setProperty ("solo", t.solo);
        auto* inst = new juce::DynamicObject();
        inst->setProperty ("type", (int) t.instrument.type);
        inst->setProperty ("params", paramsToVar (t.instrument.params));
        juce::Array<juce::var> pads;
        for (auto& p : t.instrument.padSamples) pads.add (p);
        inst->setProperty ("pads", pads);
        to->setProperty ("instrument", juce::var (inst));
        juce::Array<juce::var> fx;
        for (auto& e : t.effects)
        {
            auto* eo = new juce::DynamicObject();
            eo->setProperty ("id", e.id);
            eo->setProperty ("type", (int) e.type);
            eo->setProperty ("enabled", e.enabled);
            eo->setProperty ("params", paramsToVar (e.params));
            fx.add (juce::var (eo));
        }
        to->setProperty ("effects", fx);
        juce::Array<juce::var> slots;
        for (auto& c : t.slots) slots.add (c ? clipToVar (*c) : juce::var());
        to->setProperty ("slots", slots);
        juce::Array<juce::var> arr;
        for (auto& p : t.arrangement)
        {
            auto* po = new juce::DynamicObject();
            po->setProperty ("start", p.startBeat);
            po->setProperty ("length", p.lengthBeats);
            po->setProperty ("clip", clipToVar (*p.clip));
            arr.add (juce::var (po));
        }
        to->setProperty ("arrangement", arr);
        tr.add (juce::var (to));
    }
    o->setProperty ("tracks", tr);
    return juce::var (o);
}

Project Project::fromVar (const juce::var& v, juce::String& error)
{
    Project p;
    if (v.getProperty ("format", "").toString() != "tessera-project")
    {
        error = "Not a Tessera project file";
        return p;
    }
    p.tempo = juce::jlimit (20.0, 999.0, (double) v.getProperty ("tempo", 120.0));
    p.beatsPerBar = juce::jlimit (1, 16, (int) v.getProperty ("beatsPerBar", 4));
    p.launchQuantizeBars = juce::jlimit (0, 8, (int) v.getProperty ("launchQuantizeBars", 1));
    p.masterVolumeDb = (float) (double) v.getProperty ("masterVolumeDb", 0.0);
    p.metronome = v.getProperty ("metronome", false);
    p.loopStart = v.getProperty ("loopStart", 0.0);
    p.loopEnd = v.getProperty ("loopEnd", 16.0);
    p.loopEnabled = v.getProperty ("loopEnabled", false);
    if (auto* sc = v.getProperty ("scenes", {}).getArray())
        for (auto& s : *sc) p.scenes.push_back ({ s.toString() });
    if (auto* tr = v.getProperty ("tracks", {}).getArray())
    {
        for (auto& tv : *tr)
        {
            Track t;
            t.id = tv.getProperty ("id", Clip::newId()).toString();
            t.name = tv.getProperty ("name", "Track").toString();
            t.kind = tv.getProperty ("kind", "midi").toString() == "audio" ? TrackKind::audio : TrackKind::midi;
            t.colour = juce::Colour::fromString (tv.getProperty ("colour", "ff4fb0a5").toString());
            t.volumeDb = (float) (double) tv.getProperty ("volumeDb", 0.0);
            t.pan = juce::jlimit (-1.0f, 1.0f, (float) (double) tv.getProperty ("pan", 0.0));
            t.mute = tv.getProperty ("mute", false);
            t.solo = tv.getProperty ("solo", false);
            auto inst = tv.getProperty ("instrument", {});
            t.instrument.type = (InstrumentType) juce::jlimit (0, 2, (int) inst.getProperty ("type", 0));
            t.instrument.params = paramsFromVar (inst.getProperty ("params", {}));
            if (auto* pads = inst.getProperty ("pads", {}).getArray())
                for (int i = 0; i < juce::jmin (16, pads->size()); ++i) t.instrument.padSamples[(size_t) i] = (*pads)[i].toString();
            if (auto* fx = tv.getProperty ("effects", {}).getArray())
                for (auto& ev : *fx)
                {
                    EffectSettings e;
                    e.id = ev.getProperty ("id", Clip::newId()).toString();
                    e.type = (EffectType) juce::jlimit (0, 4, (int) ev.getProperty ("type", 0));
                    e.enabled = ev.getProperty ("enabled", true);
                    e.params = paramsFromVar (ev.getProperty ("params", {}));
                    t.effects.push_back (e);
                }
            if (auto* slots = tv.getProperty ("slots", {}).getArray())
                for (auto& s : *slots) t.slots.push_back (clipFromVar (s));
            if (auto* arr = tv.getProperty ("arrangement", {}).getArray())
                for (auto& pv : *arr)
                    if (auto c = clipFromVar (pv.getProperty ("clip", {})))
                        t.arrangement.push_back ({ c, (double) pv.getProperty ("start", 0.0), (double) pv.getProperty ("length", c->lengthBeats) });
            p.tracks.push_back (std::move (t));
        }
    }
    p.ensureSlotCount();
    return p;
}

bool Project::saveTo (const juce::File& f, juce::String& error) const
{
    auto tmp = f.getSiblingFile (f.getFileName() + ".tmp");
    if (! tmp.replaceWithText (juce::JSON::toString (toVar(), false)))
    {
        error = "Could not write " + tmp.getFullPathName();
        return false;
    }
    if (! tmp.moveFileTo (f))   // atomic replace: a crash mid-save never corrupts the project
    {
        error = "Could not replace " + f.getFullPathName();
        return false;
    }
    return true;
}

bool Project::loadFrom (const juce::File& f, Project& out, juce::String& error)
{
    juce::var v;
    auto res = juce::JSON::parse (f.loadFileAsString(), v);
    if (res.failed())
    {
        error = "Invalid project file: " + res.getErrorMessage();
        return false;
    }
    out = fromVar (v, error);
    return error.isEmpty();
}

} // namespace tessera
