#include "Views.h"

namespace tessera
{

static constexpr double defaultRecordBeats = 16.0;   // 4 bars

// ------------------------------------------------------------------ mixer strip under each column
struct SessionView::Strip : public juce::Component
{
    Strip (AppContext& c, juce::String id) : ctx (c), trackId (std::move (id))
    {
        for (auto* b : { &arm, &mute, &solo, &stop }) addAndMakeVisible (b);
        arm.setColour (juce::TextButton::buttonOnColourId, theme::record);
        mute.setColour (juce::TextButton::buttonOnColourId, theme::queued);
        solo.setColour (juce::TextButton::buttonOnColourId, theme::accent);
        arm.setTooltip ("Arm for recording / MIDI input");
        stop.setTooltip ("Stop this track's clip");
        arm.onClick = [this] { toggle ("Arm", [] (Track& t) { t.arm = ! t.arm; }); ctx.updateLiveTrack(); };
        mute.onClick = [this] { toggle ("Mute", [] (Track& t) { t.mute = ! t.mute; }); };
        solo.onClick = [this] { toggle ("Solo", [] (Track& t) { t.solo = ! t.solo; }); };
        stop.onClick = [this] { ctx.engine.stopTrack (ctx.project().trackIndex (trackId)); };

        addAndMakeVisible (vol);
        vol.setRange (-60.0, 6.0, 0.1);
        vol.setSkewFactorFromMidPoint (-12.0);
        vol.setDoubleClickReturnValue (true, 0.0);
        vol.setTextBoxStyle (juce::Slider::TextBoxBelow, false, 52, 16);
        vol.setTextValueSuffix (" dB");
        vol.onDragStart = [this] { ctx.ctl.beginGesture ("Volume"); };
        vol.onValueChange = [this]
        {
            const float v = (float) vol.getValue();
            ctx.ctl.edit ("Volume", [id = trackId, v] (Project& p) { if (auto* t = p.findTrack (id)) t->volumeDb = v; }, ! vol.isMouseButtonDown());
        };
        addAndMakeVisible (pan);
        pan.setRange (-1.0, 1.0, 0.01);
        pan.setDoubleClickReturnValue (true, 0.0);
        pan.setTooltip ("Pan");
        pan.onDragStart = [this] { ctx.ctl.beginGesture ("Pan"); };
        pan.onValueChange = [this]
        {
            const float v = (float) pan.getValue();
            ctx.ctl.edit ("Pan", [id = trackId, v] (Project& p) { if (auto* t = p.findTrack (id)) t->pan = v; }, ! pan.isMouseButtonDown());
        };
        refresh();
    }

    void toggle (const juce::String& name, std::function<void (Track&)> fn)
    {
        ctx.ctl.edit (name, [id = trackId, fn] (Project& p) { if (auto* t = p.findTrack (id)) fn (*t); });
    }

    void refresh()
    {
        if (auto* t = ctx.project().findTrack (trackId))
        {
            arm.setToggleState (t->arm, juce::dontSendNotification);
            mute.setToggleState (t->mute, juce::dontSendNotification);
            solo.setToggleState (t->solo, juce::dontSendNotification);
            if (! vol.isMouseButtonDown()) vol.setValue (t->volumeDb, juce::dontSendNotification);
            if (! pan.isMouseButtonDown()) pan.setValue (t->pan, juce::dontSendNotification);
        }
    }

    void paint (juce::Graphics& g) override
    {
        g.setColour (theme::panel);
        g.fillRect (getLocalBounds());
        const int idx = ctx.project().trackIndex (trackId);
        if (auto* rt = ctx.engine.runtimeFor (idx))
        {
            auto m = meterArea.toFloat();
            theme::drawMeter (g, m.removeFromLeft (5), rt->peakL.load());
            m.removeFromLeft (2);
            theme::drawMeter (g, m.removeFromLeft (5), rt->peakR.load());
        }
    }

    void resized() override
    {
        auto r = getLocalBounds().reduced (4);
        stop.setBounds (r.removeFromTop (20));
        r.removeFromTop (4);
        auto btns = r.removeFromTop (22);
        const int w = btns.getWidth() / 3;
        arm.setBounds (btns.removeFromLeft (w).reduced (1, 0));
        mute.setBounds (btns.removeFromLeft (w).reduced (1, 0));
        solo.setBounds (btns.reduced (1, 0));
        r.removeFromTop (4);
        pan.setBounds (r.removeFromTop (34));
        meterArea = r.removeFromRight (14).reduced (0, 2);
        vol.setBounds (r);
    }

    AppContext& ctx;
    juce::String trackId;
    juce::TextButton arm { "R" }, mute { "M" }, solo { "S" }, stop { juce::String::fromUTF8 ("\xe2\x96\xa0") };
    juce::Slider vol { juce::Slider::LinearVertical, juce::Slider::TextBoxBelow };
    juce::Slider pan { juce::Slider::RotaryHorizontalVerticalDrag, juce::Slider::NoTextBox };
    juce::Rectangle<int> meterArea;
};

// ------------------------------------------------------------------ view

SessionView::SessionView (AppContext& c) : ctx (c)
{
    ctx.ctl.addChangeListener (this);
    ctx.selectionChanged.addChangeListener (this);
    addAndMakeVisible (stopAllBtn);
    stopAllBtn.onClick = [this] { ctx.engine.stopAllClips(); };
    rebuildStrips();
    startTimerHz (20);
}

SessionView::~SessionView()
{
    ctx.ctl.removeChangeListener (this);
    ctx.selectionChanged.removeChangeListener (this);
}

void SessionView::changeListenerCallback (juce::ChangeBroadcaster*)
{
    const auto& tr = ctx.project().tracks;
    bool same = (int) tr.size() == strips.size();
    for (int i = 0; same && i < strips.size(); ++i) same = strips[i]->trackId == tr[(size_t) i].id;
    if (! same) rebuildStrips();
    for (auto* s : strips) s->refresh();
    repaint();
}

void SessionView::rebuildStrips()
{
    strips.clear();
    for (auto& t : ctx.project().tracks) addAndMakeVisible (strips.add (new Strip (ctx, t.id)));
    resized();
}

juce::Rectangle<int> SessionView::cellRect (int track, int scene) const
{
    return { track * colW - scrollX, headerH + scene * rowH, colW, rowH };
}

bool SessionView::cellAt (juce::Point<int> p, int& track, int& scene) const
{
    const int gridBottom = getHeight() - mixerH;
    if (p.y < headerH || p.y >= gridBottom || p.x >= getWidth() - sceneColW) return false;
    track = (p.x + scrollX) / colW;
    scene = (p.y - headerH) / rowH;
    return track >= 0 && track < (int) ctx.project().tracks.size() && scene >= 0 && scene < (int) ctx.project().scenes.size();
}

void SessionView::resized()
{
    const int y = getHeight() - mixerH;
    for (int i = 0; i < strips.size(); ++i) strips[i]->setBounds (i * colW - scrollX, y, colW, mixerH);
    stopAllBtn.setBounds (getWidth() - sceneColW + 6, y + 4, sceneColW - 12, 22);
}

void SessionView::paint (juce::Graphics& g)
{
    const auto& p = ctx.project();
    g.fillAll (theme::bg);
    const int gridBottom = getHeight() - mixerH;
    const int sceneX = getWidth() - sceneColW;
    const double beat = ctx.engine.positionBeats();
    const bool blink = std::fmod (beat, 1.0) < 0.5;

    for (int ti = 0; ti < (int) p.tracks.size(); ++ti)
    {
        const auto& t = p.tracks[(size_t) ti];
        const int x = ti * colW - scrollX;
        if (x > sceneX || x + colW < 0) continue;
        // header
        auto h = juce::Rectangle<int> (x, 0, colW, headerH).reduced (1);
        const bool selected = ctx.selection.trackId == t.id;
        g.setColour (selected ? theme::panelHi.brighter (0.1f) : theme::panelHi);
        g.fillRect (h);
        g.setColour (t.colour);
        g.fillRect (h.removeFromTop (3));
        g.setColour (theme::text);
        g.setFont (theme::font (13.0f, true));
        g.drawText (t.name, h.reduced (6, 0), juce::Justification::centredLeft);
        g.setColour (theme::textDim);
        g.setFont (theme::font (10.0f));
        g.drawText (t.kind == TrackKind::midi ? "MIDI" : "AUDIO", h.reduced (6, 0), juce::Justification::centredRight);

        auto* rt = ctx.engine.runtimeFor (ti);
        const int playing = rt ? rt->playingSlot.load() : -1;
        const int queued = rt ? rt->queuedSlot.load() : -1;
        const int recSlot = rt ? rt->recordingSlot.load() : -1;
        for (int si = 0; si < (int) p.scenes.size(); ++si)
        {
            auto r = cellRect (ti, si).reduced (2, 1);
            if (r.getBottom() > gridBottom) break;
            const auto& clip = si < (int) t.slots.size() ? t.slots[(size_t) si] : nullptr;
            const bool sel = ctx.selection.where == Selection::Where::slot && ctx.selection.trackId == t.id && ctx.selection.slot == si;
            if (clip)
            {
                g.setColour (clip->colour.withAlpha (si == playing ? 0.95f : 0.7f));
                g.fillRoundedRectangle (r.toFloat(), 3);
                if (si == playing && rt)
                {
                    g.setColour (juce::Colours::black.withAlpha (0.25f));
                    g.fillRect (r.withWidth ((int) (r.getWidth() * rt->clipPhase.load())).withTop (r.getBottom() - 3));
                }
                juce::Path tri;
                auto tr = r.removeFromLeft (18).toFloat().withSizeKeepingCentre (9, 10);
                tri.addTriangle (tr.getTopLeft(), tr.getBottomLeft(), { tr.getRight(), tr.getCentreY() });
                g.setColour (si == playing ? theme::play : (si == queued && blink) ? theme::queued : juce::Colours::black.withAlpha (0.55f));
                g.fillPath (tri);
                g.setColour (juce::Colours::black.withAlpha (0.85f));
                g.setFont (theme::font (12.0f));
                g.drawText (clip->name, r.reduced (2, 0), juce::Justification::centredLeft, true);
            }
            else
            {
                g.setColour (theme::cell);
                g.fillRoundedRectangle (r.toFloat(), 3);
                auto dot = r.withSizeKeepingCentre (8, 8).toFloat();
                if (si == recSlot) { g.setColour (blink ? theme::record : theme::record.darker()); g.fillEllipse (dot.expanded (2)); }
                else if (t.arm && t.kind == TrackKind::midi) { g.setColour (theme::record.withAlpha (0.6f)); g.drawEllipse (dot, 1.5f); }
                else { g.setColour (theme::line); g.fillRect (dot.withSizeKeepingCentre (6, 6)); }
            }
            if (sel) { g.setColour (theme::text); g.drawRoundedRectangle (cellRect (ti, si).reduced (2, 1).toFloat(), 3, 1.5f); }
        }
    }

    // scene column
    g.setColour (theme::panel);
    g.fillRect (sceneX, 0, sceneColW, gridBottom);
    g.setColour (theme::textDim);
    g.setFont (theme::font (11.0f, true));
    g.drawText ("SCENES", sceneX, 0, sceneColW, headerH, juce::Justification::centred);
    for (int si = 0; si < (int) p.scenes.size(); ++si)
    {
        auto r = juce::Rectangle<int> (sceneX + 4, headerH + si * rowH, sceneColW - 8, rowH).reduced (0, 1);
        if (r.getBottom() > gridBottom) break;
        g.setColour (theme::cell);
        g.fillRoundedRectangle (r.toFloat(), 3);
        juce::Path tri;
        auto tr = r.removeFromLeft (18).toFloat().withSizeKeepingCentre (9, 10);
        tri.addTriangle (tr.getTopLeft(), tr.getBottomLeft(), { tr.getRight(), tr.getCentreY() });
        g.setColour (theme::textDim);
        g.fillPath (tri);
        g.setColour (theme::text);
        g.setFont (theme::font (12.0f));
        g.drawText (p.scenes[(size_t) si].name, r, juce::Justification::centredLeft);
    }
    g.setColour (theme::line);
    g.drawHorizontalLine (gridBottom, 0, (float) getWidth());
    if (p.tracks.empty())
    {
        g.setColour (theme::textDim);
        g.drawText ("Right-click to add a track", getLocalBounds().withBottom (gridBottom), juce::Justification::centred);
    }
}

void SessionView::mouseDown (const juce::MouseEvent& e)
{
    const auto& p = ctx.project();
    const int sceneX = getWidth() - sceneColW;
    const int gridBottom = getHeight() - mixerH;
    if (e.y < headerH && e.x < sceneX)
    {
        const int ti = (e.x + scrollX) / colW;
        if (ti >= 0 && ti < (int) p.tracks.size())
        {
            ctx.select (p.tracks[(size_t) ti].id);
            if (e.mods.isPopupMenu()) trackMenu (ti);
        }
        else if (e.mods.isPopupMenu()) trackMenu (-1);
        return;
    }
    if (e.x >= sceneX && e.y >= headerH && e.y < gridBottom)
    {
        const int si = (e.y - headerH) / rowH;
        if (si < 0 || si >= (int) p.scenes.size()) return;
        if (e.mods.isPopupMenu()) sceneMenu (si);
        else ctx.engine.launchScene (si);
        return;
    }
    int ti, si;
    if (! cellAt (e.getPosition(), ti, si))
    {
        if (e.mods.isPopupMenu() && e.y < gridBottom) trackMenu (-1);
        return;
    }
    const auto& t = p.tracks[(size_t) ti];
    const auto& clip = t.slots[(size_t) si];
    if (e.mods.isPopupMenu()) { ctx.select (t.id, clip ? Selection::Where::slot : Selection::Where::none, si); clipMenu (ti, si); return; }
    const bool onLaunch = e.x - cellRect (ti, si).getX() < 22;
    if (clip)
    {
        ctx.select (t.id, Selection::Where::slot, si);
        if (onLaunch) ctx.engine.launchClip (ti, si);
    }
    else
    {
        ctx.select (t.id);
        if (t.arm && t.kind == TrackKind::midi) ctx.engine.recordIntoSlot (ti, si, defaultRecordBeats);
        else ctx.engine.stopTrack (ti);
    }
}

void SessionView::mouseDoubleClick (const juce::MouseEvent& e)
{
    int ti, si;
    if (! cellAt (e.getPosition(), ti, si)) return;
    const auto& t = ctx.project().tracks[(size_t) ti];
    if (t.slots[(size_t) si] != nullptr || t.kind != TrackKind::midi) return;
    auto clip = std::make_shared<Clip>();
    clip->id = Clip::newId();
    clip->name = "Clip";
    clip->colour = t.colour;
    clip->lengthBeats = 4.0;
    ctx.ctl.edit ("New clip", [id = t.id, si, clip] (Project& p) { if (auto* tr = p.findTrack (id)) tr->slots[(size_t) si] = clip; });
    ctx.select (t.id, Selection::Where::slot, si);
}

void SessionView::trackMenu (int ti)
{
    juce::PopupMenu m;
    m.addItem (1, "Add MIDI track");
    m.addItem (2, "Add audio track");
    if (ti >= 0)
    {
        m.addSeparator();
        m.addItem (3, "Rename track...");
        m.addItem (4, "Duplicate track");
        m.addItem (5, "Delete track");
    }
    m.showMenuAsync ({}, [this, ti] (int r)
    {
        const auto& p = ctx.project();
        if (r == 1 || r == 2)
        {
            const auto kind = r == 1 ? TrackKind::midi : TrackKind::audio;
            const int n = (int) p.tracks.size();
            ctx.ctl.edit ("Add track", [kind, n] (Project& pr)
            {
                pr.tracks.push_back (makeTrack (kind, kind == TrackKind::midi ? "MIDI " + juce::String (n + 1) : "Audio " + juce::String (n + 1), n));
            });
        }
        else if (r == 3 && ti >= 0)
        {
            auto* w = new juce::AlertWindow ("Rename track", {}, juce::MessageBoxIconType::NoIcon);
            w->addTextEditor ("name", p.tracks[(size_t) ti].name);
            w->addButton ("OK", 1, juce::KeyPress (juce::KeyPress::returnKey));
            w->addButton ("Cancel", 0);
            w->enterModalState (true, juce::ModalCallbackFunction::create ([this, w, id = p.tracks[(size_t) ti].id] (int res)
            {
                const auto name = w->getTextEditorContents ("name").trim();
                if (res == 1 && name.isNotEmpty())
                    ctx.ctl.edit ("Rename track", [id, name] (Project& pr) { if (auto* t = pr.findTrack (id)) t->name = name; });
            }), true);
        }
        else if (r == 4 && ti >= 0)
            ctx.ctl.edit ("Duplicate track", [ti] (Project& pr)
            {
                auto copy = pr.tracks[(size_t) ti];
                copy.id = Clip::newId();
                copy.name += " copy";
                copy.arm = false;
                for (auto& e : copy.effects) e.id = Clip::newId();   // separate processors
                pr.tracks.insert (pr.tracks.begin() + ti + 1, copy);
            });
        else if (r == 5 && ti >= 0)
            ctx.ctl.edit ("Delete track", [ti] (Project& pr) { pr.tracks.erase (pr.tracks.begin() + ti); });
    });
}

void SessionView::clipMenu (int ti, int si)
{
    const auto& t = ctx.project().tracks[(size_t) ti];
    const bool has = t.slots[(size_t) si] != nullptr;
    juce::PopupMenu m;
    if (! has && t.kind == TrackKind::midi) m.addItem (1, "Create MIDI clip");
    if (has)
    {
        m.addItem (2, "Launch");
        m.addItem (3, "Rename...");
        m.addItem (4, "Duplicate to next empty slot");
        m.addItem (5, "Copy to arrangement at playhead");
        m.addSeparator();
        m.addItem (6, "Delete clip");
    }
    if (t.arm && t.kind == TrackKind::midi && ! has) m.addItem (7, "Record 4 bars into this slot");
    m.showMenuAsync ({}, [this, ti, si, id = t.id] (int r)
    {
        if (r == 1)
        {
            auto clip = std::make_shared<Clip>();
            clip->id = Clip::newId();
            clip->name = "Clip";
            clip->colour = ctx.project().tracks[(size_t) ti].colour;
            ctx.ctl.edit ("New clip", [id, si, clip] (Project& p) { if (auto* tr = p.findTrack (id)) tr->slots[(size_t) si] = clip; });
            ctx.select (id, Selection::Where::slot, si);
        }
        else if (r == 2) ctx.engine.launchClip (ti, si);
        else if (r == 3)
        {
            auto* w = new juce::AlertWindow ("Rename clip", {}, juce::MessageBoxIconType::NoIcon);
            w->addTextEditor ("name", ctx.project().tracks[(size_t) ti].slots[(size_t) si]->name);
            w->addButton ("OK", 1, juce::KeyPress (juce::KeyPress::returnKey));
            w->addButton ("Cancel", 0);
            w->enterModalState (true, juce::ModalCallbackFunction::create ([this, w, id, si] (int res)
            {
                const auto name = w->getTextEditorContents ("name").trim();
                if (res == 1 && name.isNotEmpty())
                {
                    ctx.select (id, Selection::Where::slot, si);
                    ctx.updateSelectedClip ("Rename clip", [name] (Clip& c) { c.name = name; });
                }
            }), true);
        }
        else if (r == 4)
            ctx.ctl.edit ("Duplicate clip", [id, si] (Project& p)
            {
                auto* tr = p.findTrack (id);
                if (tr == nullptr) return;
                for (size_t k = (size_t) si + 1; k < tr->slots.size(); ++k)
                    if (tr->slots[k] == nullptr) { auto c = std::make_shared<Clip> (*tr->slots[(size_t) si]); c->id = Clip::newId(); tr->slots[k] = c; return; }
                p.scenes.push_back ({ juce::String (p.scenes.size() + 1) });
                p.ensureSlotCount();
                auto c = std::make_shared<Clip> (*tr->slots[(size_t) si]); c->id = Clip::newId(); tr->slots.back() = c;
            });
        else if (r == 5)
        {
            const double at = std::floor (ctx.engine.positionBeats());
            ctx.ctl.edit ("Copy to arrangement", [id, si, at] (Project& p)
            {
                auto* tr = p.findTrack (id);
                if (tr == nullptr || ! tr->slots[(size_t) si]) return;
                auto c = std::make_shared<Clip> (*tr->slots[(size_t) si]);
                c->id = Clip::newId();
                tr->arrangement.push_back ({ c, at, c->lengthBeats });
            });
        }
        else if (r == 6)
        {
            ctx.ctl.edit ("Delete clip", [id, si] (Project& p) { if (auto* tr = p.findTrack (id)) tr->slots[(size_t) si] = nullptr; });
            ctx.select (id);
        }
        else if (r == 7) ctx.engine.recordIntoSlot (ti, si, defaultRecordBeats);
    });
}

void SessionView::sceneMenu (int si)
{
    juce::PopupMenu m;
    m.addItem (1, "Launch scene");
    m.addItem (2, "Insert scene below");
    m.addItem (3, "Delete scene", ctx.project().scenes.size() > 1);
    m.showMenuAsync ({}, [this, si] (int r)
    {
        if (r == 1) ctx.engine.launchScene (si);
        else if (r == 2)
            ctx.ctl.edit ("Insert scene", [si] (Project& p)
            {
                p.scenes.insert (p.scenes.begin() + si + 1, Scene { juce::String (p.scenes.size() + 1) });
                for (auto& t : p.tracks) { t.slots.resize (p.scenes.size() - 1); t.slots.insert (t.slots.begin() + si + 1, nullptr); }
            });
        else if (r == 3)
            ctx.ctl.edit ("Delete scene", [si] (Project& p)
            {
                p.scenes.erase (p.scenes.begin() + si);
                for (auto& t : p.tracks) if (si < (int) t.slots.size()) t.slots.erase (t.slots.begin() + si);
            });
    });
}

// ------------------------------------------------------------------ drag & drop of audio files

bool SessionView::isInterestedInFileDrag (const juce::StringArray& files)
{
    for (auto& f : files) if (AppContext::isAudioFile (f)) return true;
    return false;
}

void SessionView::filesDropped (const juce::StringArray& files, int x, int y)
{
    int offset = 0;
    for (auto& f : files)
        if (AppContext::isAudioFile (f)) dropAudioAt (juce::File (f), { x, y + (offset++) * rowH });
}

bool SessionView::isInterestedInDragSource (const SourceDetails& d) { return d.description == "TesseraFile"; }

void SessionView::itemDropped (const SourceDetails& d)
{
    if (ctx.browserSelectedFile) dropAudioAt (ctx.browserSelectedFile(), d.localPosition);
}

void SessionView::dropAudioAt (const juce::File& f, juce::Point<int> pos)
{
    int ti, si;
    const auto& p = ctx.project();
    auto clip = AppContext::audioClipFromFile (f, p.tempo, paletteColour ((int) p.tracks.size()));
    if (clip == nullptr) return;
    if (cellAt (pos, ti, si) && p.tracks[(size_t) ti].kind == TrackKind::audio)
    {
        clip->colour = p.tracks[(size_t) ti].colour;
        ctx.ctl.edit ("Add audio clip", [id = p.tracks[(size_t) ti].id, si, clip] (Project& pr) { if (auto* t = pr.findTrack (id)) t->slots[(size_t) si] = clip; });
        ctx.select (p.tracks[(size_t) ti].id, Selection::Where::slot, si);
    }
    else
    {   // dropped elsewhere (or on a MIDI track): create a new audio track for it
        const int n = (int) p.tracks.size();
        ctx.ctl.edit ("Add audio clip", [clip, n] (Project& pr)
        {
            auto t = makeTrack (TrackKind::audio, clip->name, n);
            pr.ensureSlotCount();
            t.slots.resize (pr.scenes.size());
            clip->colour = t.colour;
            t.slots[0] = clip;
            pr.tracks.push_back (t);
        });
        ctx.select (ctx.project().tracks.back().id, Selection::Where::slot, 0);
    }
}

} // namespace tessera
