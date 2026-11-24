#pragma once
#include "../Engine/AudioEngine.h"
#include <juce_gui_extra/juce_gui_extra.h>

namespace tessera
{

// What the clip editor / device view are showing.
struct Selection
{
    juce::String trackId;
    enum class Where { none, slot, arrangement } where = Where::none;
    int slot = -1;           // session slot index
    juce::String clipId;     // arrangement: clip id of the placement
};

// Shared services passed to every view.
struct AppContext
{
    ProjectController& ctl;
    AudioEngine& engine;
    Selection selection;
    juce::ChangeBroadcaster selectionChanged;
    std::function<juce::File()> browserSelectedFile;   // for drags that start in the browser
    std::atomic<int> liveTrackIndex { -1 };             // track receiving MIDI/computer-keyboard input

    AppContext (ProjectController& c, AudioEngine& e) : ctl (c), engine (e) {}

    const Project& project() const { return ctl.project(); }

    void select (const juce::String& trackId, Selection::Where w = Selection::Where::none, int slot = -1, const juce::String& clipId = {})
    {
        selection = { trackId, w, slot, clipId };
        updateLiveTrack();
        selectionChanged.sendChangeMessage();
    }

    // MIDI input goes to the first armed MIDI track, otherwise to the selected MIDI track.
    void updateLiveTrack()
    {
        const auto& p = project();
        int idx = -1;
        for (size_t i = 0; i < p.tracks.size(); ++i)
            if (p.tracks[i].arm && p.tracks[i].kind == TrackKind::midi) { idx = (int) i; break; }
        if (idx < 0)
        {
            const int s = p.trackIndex (selection.trackId);
            if (s >= 0 && p.tracks[(size_t) s].kind == TrackKind::midi) idx = s;
        }
        liveTrackIndex = idx;
    }

    // The clip currently selected (session slot or arrangement placement), or nullptr.
    ClipPtr selectedClip() const
    {
        const auto* t = project().findTrack (selection.trackId);
        if (t == nullptr) return nullptr;
        if (selection.where == Selection::Where::slot && selection.slot >= 0 && selection.slot < (int) t->slots.size())
            return t->slots[(size_t) selection.slot];
        if (selection.where == Selection::Where::arrangement)
            for (auto& pl : t->arrangement) if (pl.clip->id == selection.clipId) return pl.clip;
        return nullptr;
    }

    // Replace the selected clip with an edited copy (undoable).
    void updateSelectedClip (const juce::String& undoName, const std::function<void (Clip&)>& fn, bool undoable = true)
    {
        auto sel = selection;
        ctl.edit (undoName, [sel, fn] (Project& p)
        {
            auto* t = p.findTrack (sel.trackId);
            if (t == nullptr) return;
            auto apply = [&] (ClipPtr& c) { if (c) { auto n = std::make_shared<Clip> (*c); fn (*n); c = n; } };
            if (sel.where == Selection::Where::slot && sel.slot >= 0 && sel.slot < (int) t->slots.size()) apply (t->slots[(size_t) sel.slot]);
            if (sel.where == Selection::Where::arrangement)
                for (auto& pl : t->arrangement)
                    if (pl.clip->id == sel.clipId)
                    {
                        apply (pl.clip);
                        if (! pl.clip->looping) pl.lengthBeats = pl.clip->lengthBeats;
                    }
        }, undoable);
    }

    // Audio clip from a file, length derived from the file duration at `tempo`.
    static std::shared_ptr<Clip> audioClipFromFile (const juce::File& f, double tempo, juce::Colour colour)
    {
        const double secs = AudioFileCache::durationSeconds (f);
        if (secs <= 0) return nullptr;
        auto c = std::make_shared<Clip>();
        c->id = Clip::newId();
        c->kind = ClipKind::audio;
        c->name = f.getFileNameWithoutExtension();
        c->audioFile = f.getFullPathName();
        c->colour = colour;
        c->sourceTempo = tempo;
        c->lengthBeats = juce::jmax (0.25, std::round (secs * tempo / 60.0 * 4.0) / 4.0);
        c->warp = true;
        return c;
    }

    static bool isAudioFile (const juce::String& path)
    {
        return juce::File (path).hasFileExtension ("wav;aif;aiff;flac;ogg;mp3;m4a;caf");
    }
};

} // namespace tessera
