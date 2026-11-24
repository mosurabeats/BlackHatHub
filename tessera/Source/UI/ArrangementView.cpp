#include "Views.h"

namespace tessera
{

ArrangementView::ArrangementView (AppContext& c) : ctx (c)
{
    ctx.ctl.addChangeListener (this);
    ctx.selectionChanged.addChangeListener (this);
    setWantsKeyboardFocus (true);
    startTimerHz (30);
}

ArrangementView::~ArrangementView()
{
    ctx.ctl.removeChangeListener (this);
    ctx.selectionChanged.removeChangeListener (this);
}

void ArrangementView::timerCallback()
{
    if (! isShowing()) return;
    if (ctx.engine.isPlaying())
    {   // follow the playhead
        const int x = beatToX (ctx.engine.positionBeats());
        if (x > getWidth() - 40) scrollBeats = ctx.engine.positionBeats() - 4.0;
        else if (x < headerW) scrollBeats = juce::jmax (0.0, ctx.engine.positionBeats() - 1.0);
    }
    repaint();
}

void ArrangementView::resized() {}

double ArrangementView::snap (double beat) const
{
    const double grid = pxPerBeat >= 48 ? 0.25 : pxPerBeat >= 16 ? 1.0 : 4.0;
    return juce::jmax (0.0, std::round (beat / grid) * grid);
}

bool ArrangementView::hitPlacement (juce::Point<int> p, int& track, int& index, bool& edge) const
{
    track = laneAt (p.y);
    const auto& pr = ctx.project();
    if (track < 0 || track >= (int) pr.tracks.size() || p.x < headerW) return false;
    const auto& arr = pr.tracks[(size_t) track].arrangement;
    for (int i = (int) arr.size() - 1; i >= 0; --i)
    {
        const int x0 = beatToX (arr[(size_t) i].startBeat), x1 = beatToX (arr[(size_t) i].startBeat + arr[(size_t) i].lengthBeats);
        if (p.x >= x0 && p.x <= x1)
        {
            index = i;
            edge = p.x >= x1 - 6;
            return true;
        }
    }
    return false;
}

void ArrangementView::paint (juce::Graphics& g)
{
    const auto& p = ctx.project();
    g.fillAll (theme::bg);
    const int bpb = juce::jmax (1, p.beatsPerBar);
    const double firstBeat = std::floor (scrollBeats);
    const double lastBeat = xToBeat (getWidth());

    // lanes + grid
    for (int ti = 0; ti < (int) p.tracks.size(); ++ti)
    {
        const int y = rulerH + ti * laneH - scrollY;
        if (y + laneH < rulerH || y > getHeight()) continue;
        g.setColour (ti % 2 ? theme::bg : theme::bg.brighter (0.03f));
        g.fillRect (headerW, y, getWidth() - headerW, laneH);
    }
    for (double b = firstBeat; b <= lastBeat; b += 1.0)
    {
        const int x = beatToX (b);
        const bool bar = ((int) b) % bpb == 0;
        if (! bar && pxPerBeat < 10) continue;
        g.setColour (bar ? theme::line : theme::line.withAlpha (0.4f));
        g.drawVerticalLine (x, (float) rulerH, (float) getHeight());
    }
    // loop region
    if (p.loopEnd > p.loopStart)
    {
        const int x0 = beatToX (p.loopStart), x1 = beatToX (p.loopEnd);
        g.setColour ((p.loopEnabled ? theme::accent : theme::textDim).withAlpha (p.loopEnabled ? 0.10f : 0.04f));
        g.fillRect (juce::Rectangle<int>::leftTopRightBottom (juce::jmax (headerW, x0), rulerH, x1, getHeight()));
    }
    // clips
    for (int ti = 0; ti < (int) p.tracks.size(); ++ti)
    {
        const auto& t = p.tracks[(size_t) ti];
        const int y = rulerH + ti * laneH - scrollY;
        if (y + laneH < rulerH || y > getHeight()) continue;
        for (auto& pl : t.arrangement)
        {
            const int x0 = beatToX (pl.startBeat), x1 = beatToX (pl.startBeat + pl.lengthBeats);
            if (x1 < headerW || x0 > getWidth()) continue;
            auto r = juce::Rectangle<int>::leftTopRightBottom (juce::jmax (headerW, x0), y + 3, x1, y + laneH - 3);
            const bool sel = ctx.selection.where == Selection::Where::arrangement && ctx.selection.clipId == pl.clip->id;
            g.setColour (pl.clip->colour.withAlpha (0.85f));
            g.fillRoundedRectangle (r.toFloat(), 3);
            g.setColour (juce::Colours::black.withAlpha (0.6f));
            g.setFont (theme::font (11.5f, true));
            g.drawText (pl.clip->name, r.reduced (4, 2).removeFromTop (14), juce::Justification::topLeft, true);
            auto body = r.reduced (2).withTrimmedTop (14);
            if (pl.clip->kind == ClipKind::midi && ! pl.clip->notes.empty())
            {
                int lo = 127, hi = 0;
                for (auto& n : pl.clip->notes) { lo = juce::jmin (lo, n.pitch); hi = juce::jmax (hi, n.pitch); }
                const float span = (float) juce::jmax (12, hi - lo + 1);
                const double L = pl.clip->lengthBeats;
                for (double it = 0; it < pl.lengthBeats; it += L)
                {
                    for (auto& n : pl.clip->notes)
                    {
                        if (it + n.start >= pl.lengthBeats) continue;
                        const float nx = (float) beatToX (pl.startBeat + it + n.start);
                        const float nw = juce::jmax (1.5f, (float) (juce::jmin (n.length, pl.lengthBeats - it - n.start) * pxPerBeat));
                        const float ny = body.getBottom() - (n.pitch - lo + 1) / span * body.getHeight();
                        g.fillRect (nx, ny, nw, juce::jmax (1.5f, body.getHeight() / span));
                    }
                    if (! pl.clip->looping) break;
                }
            }
            else if (pl.clip->kind == ClipKind::audio)
            {
                g.setColour (juce::Colours::black.withAlpha (0.35f));
                g.drawHorizontalLine (body.getCentreY(), (float) body.getX(), (float) body.getRight());
                g.setFont (theme::font (10.0f));
                g.drawText (juce::File (pl.clip->audioFile).getFileName(), body, juce::Justification::centredLeft, true);
            }
            if (sel) { g.setColour (theme::text); g.drawRoundedRectangle (r.toFloat(), 3, 2); }
        }
    }
    // track headers
    for (int ti = 0; ti < (int) p.tracks.size(); ++ti)
    {
        const auto& t = p.tracks[(size_t) ti];
        const int y = rulerH + ti * laneH - scrollY;
        auto r = juce::Rectangle<int> (0, y, headerW, laneH).reduced (0, 1);
        g.setColour (ctx.selection.trackId == t.id ? theme::panelHi.brighter (0.08f) : theme::panelHi);
        g.fillRect (r);
        g.setColour (t.colour);
        g.fillRect (r.removeFromLeft (4));
        g.setColour (theme::text);
        g.setFont (theme::font (13.0f, true));
        g.drawText (t.name, r.reduced (8, 4).removeFromTop (18), juce::Justification::centredLeft);
        auto btns = r.reduced (8, 6).removeFromBottom (18);
        auto drawBtn = [&] (const char* label, bool on, juce::Colour c)
        {
            auto b = btns.removeFromLeft (24);
            btns.removeFromLeft (4);
            g.setColour (on ? c : theme::cell);
            g.fillRoundedRectangle (b.toFloat(), 2);
            g.setColour (on ? theme::bg : theme::textDim);
            g.setFont (theme::font (11.0f, true));
            g.drawText (label, b, juce::Justification::centred);
        };
        drawBtn ("M", t.mute, theme::queued);
        drawBtn ("S", t.solo, theme::accent);
        drawBtn ("R", t.arm, theme::record);
    }
    // ruler
    g.setColour (theme::panel);
    g.fillRect (0, 0, getWidth(), rulerH);
    g.setFont (theme::font (11.0f));
    for (double b = firstBeat; b <= lastBeat; b += 1.0)
    {
        if (((int) b) % bpb != 0) continue;
        const int bar = (int) b / bpb + 1;
        if (pxPerBeat * bpb < 30 && bar % 4 != 1) continue;
        const int x = beatToX (b);
        if (x < headerW) continue;
        g.setColour (theme::textDim);
        g.drawVerticalLine (x, 12.0f, (float) rulerH);
        g.drawText (juce::String (bar), x + 3, 0, 40, rulerH - 4, juce::Justification::bottomLeft);
    }
    if (p.loopEnd > p.loopStart)
    {
        g.setColour (p.loopEnabled ? theme::accent : theme::textDim);
        g.fillRect (juce::Rectangle<int>::leftTopRightBottom (juce::jmax (headerW, beatToX (p.loopStart)), 0, beatToX (p.loopEnd), 5));
    }
    g.setColour (theme::textDim);
    g.drawText ("Drag ruler: locate  |  Shift-drag: loop", 6, 0, headerW - 8, rulerH, juce::Justification::centredLeft, true);
    // playhead
    const int px = beatToX (ctx.engine.positionBeats());
    if (px >= headerW)
    {
        g.setColour (ctx.engine.isRecording() ? theme::record : theme::text);
        g.drawVerticalLine (px, 0.0f, (float) getHeight());
    }
    if (p.tracks.empty())
    {
        g.setColour (theme::textDim);
        g.drawText ("Add tracks from the Session view or the Create menu.", getLocalBounds(), juce::Justification::centred);
    }
}

void ArrangementView::mouseMove (const juce::MouseEvent& e)
{
    int t, i; bool edge;
    setMouseCursor (hitPlacement (e.getPosition(), t, i, edge) && edge ? juce::MouseCursor::LeftRightResizeCursor : juce::MouseCursor::NormalCursor);
}

void ArrangementView::mouseDown (const juce::MouseEvent& e)
{
    grabKeyboardFocus();
    const auto& p = ctx.project();
    drag = Drag::none;
    dragBegun = false;
    if (e.y < rulerH)
    {
        dragStartBeat = snap (xToBeat (e.x));
        drag = e.mods.isShiftDown() ? Drag::loop : Drag::scrub;
        if (drag == Drag::scrub) ctx.engine.locate (dragStartBeat);
        return;
    }
    const int lane = laneAt (e.y);
    if (lane < 0 || lane >= (int) p.tracks.size()) return;
    const auto& t = p.tracks[(size_t) lane];
    if (e.x < headerW)
    {   // header buttons
        ctx.select (t.id);
        const int bx = e.x - 8, by = e.y - (rulerH + lane * laneH - scrollY);
        if (by > laneH - 26)
        {
            const int which = bx / 28;
            auto toggle = [&] (const char* name, std::function<void (Track&)> fn)
            { ctx.ctl.edit (name, [id = t.id, fn] (Project& pr) { if (auto* tr = pr.findTrack (id)) fn (*tr); }); };
            if (which == 0) toggle ("Mute", [] (Track& tr) { tr.mute = ! tr.mute; });
            else if (which == 1) toggle ("Solo", [] (Track& tr) { tr.solo = ! tr.solo; });
            else if (which == 2) { toggle ("Arm", [] (Track& tr) { tr.arm = ! tr.arm; }); ctx.updateLiveTrack(); }
        }
        return;
    }
    int ti, idx; bool edge;
    if (hitPlacement (e.getPosition(), ti, idx, edge))
    {
        const auto& pl = t.arrangement[(size_t) idx];
        ctx.select (t.id, Selection::Where::arrangement, -1, pl.clip->id);
        if (e.mods.isPopupMenu())
        {
            juce::PopupMenu m;
            m.addItem (1, "Duplicate after");
            m.addItem (2, pl.clip->looping ? "Disable looping" : "Enable looping");
            m.addItem (3, "Delete");
            m.showMenuAsync ({}, [this, id = t.id, clipId = pl.clip->id] (int r)
            {
                if (r == 1)
                    ctx.ctl.edit ("Duplicate clip", [id, clipId] (Project& pr)
                    {
                        if (auto* tr = pr.findTrack (id))
                            for (auto& q : tr->arrangement)
                                if (q.clip->id == clipId)
                                {
                                    auto c = std::make_shared<Clip> (*q.clip); c->id = Clip::newId();
                                    tr->arrangement.push_back ({ c, q.startBeat + q.lengthBeats, q.lengthBeats });
                                    return;
                                }
                    });
                else if (r == 2) ctx.updateSelectedClip ("Loop", [] (Clip& c) { c.looping = ! c.looping; });
                else if (r == 3) deleteSelected();
            });
            return;
        }
        drag = edge ? Drag::resize : Drag::move;
        dragTrack = dragOrigTrack = lane;
        dragIndex = idx;
        dragStartBeat = xToBeat (e.x);
        dragOrigStart = pl.startBeat;
        dragOrigLen = pl.lengthBeats;
    }
    else
    {
        ctx.select (t.id);
        ctx.engine.locate (snap (xToBeat (e.x)));
    }
}

void ArrangementView::mouseDrag (const juce::MouseEvent& e)
{
    const double beat = xToBeat (e.x);
    if (drag == Drag::scrub) { ctx.engine.locate (snap (beat)); return; }
    if (drag == Drag::loop)
    {
        const double a = juce::jmin (dragStartBeat, snap (beat)), b = juce::jmax (dragStartBeat, snap (beat));
        if (b - a < 0.25) return;
        ctx.ctl.edit ("Loop region", [a, b] (Project& p) { p.loopStart = a; p.loopEnd = b; p.loopEnabled = true; }, false);
        return;
    }
    if (drag != Drag::move && drag != Drag::resize) return;
    if (! dragBegun) { ctx.ctl.beginGesture (drag == Drag::move ? "Move clip" : "Resize clip"); dragBegun = true; }
    const auto clipId = ctx.selection.clipId;
    const int origTrack = dragOrigTrack;
    if (drag == Drag::move)
    {
        const double start = snap (dragOrigStart + beat - dragStartBeat);
        int target = juce::jlimit (0, (int) ctx.project().tracks.size() - 1, laneAt (e.y));
        if (ctx.project().tracks[(size_t) target].kind != ctx.project().tracks[(size_t) origTrack].kind) target = dragTrack;
        const int from = dragTrack;
        ctx.ctl.edit ("Move clip", [clipId, start, from, target] (Project& p)
        {
            auto& src = p.tracks[(size_t) from].arrangement;
            for (size_t i = 0; i < src.size(); ++i)
                if (src[i].clip->id == clipId)
                {
                    auto pl = src[i];
                    pl.startBeat = start;
                    src.erase (src.begin() + (long) i);
                    p.tracks[(size_t) target].arrangement.push_back (pl);
                    return;
                }
        }, false);
        if (target != dragTrack) { dragTrack = target; ctx.selection.trackId = ctx.project().tracks[(size_t) target].id; }
    }
    else
    {
        const double len = juce::jmax (0.25, snap (dragOrigStart + dragOrigLen + beat - dragStartBeat) - dragOrigStart);
        const int ti = dragTrack;
        ctx.ctl.edit ("Resize clip", [clipId, len, ti] (Project& p)
        {
            for (auto& pl : p.tracks[(size_t) ti].arrangement)
                if (pl.clip->id == clipId)
                {
                    pl.lengthBeats = len;
                    if (! pl.clip->looping)
                    {   // a non-looping clip is trimmed/extended rather than repeated
                        auto c = std::make_shared<Clip> (*pl.clip);
                        c->lengthBeats = len;
                        pl.clip = c;
                    }
                }
        }, false);
    }
}

void ArrangementView::mouseUp (const juce::MouseEvent&) { drag = Drag::none; }

void ArrangementView::mouseDoubleClick (const juce::MouseEvent& e)
{
    const int lane = laneAt (e.y);
    const auto& p = ctx.project();
    if (e.x < headerW || lane < 0 || lane >= (int) p.tracks.size()) return;
    int ti, idx; bool edge;
    if (hitPlacement (e.getPosition(), ti, idx, edge)) return;
    const auto& t = p.tracks[(size_t) lane];
    if (t.kind != TrackKind::midi) return;
    auto clip = std::make_shared<Clip>();
    clip->id = Clip::newId();
    clip->name = "Clip";
    clip->colour = t.colour;
    clip->lengthBeats = (double) p.beatsPerBar;
    const double at = std::floor (xToBeat (e.x) / p.beatsPerBar) * p.beatsPerBar;
    ctx.ctl.edit ("New clip", [id = t.id, clip, at] (Project& pr) { if (auto* tr = pr.findTrack (id)) tr->arrangement.push_back ({ clip, at, clip->lengthBeats }); });
    ctx.select (t.id, Selection::Where::arrangement, -1, clip->id);
}

void ArrangementView::mouseWheelMove (const juce::MouseEvent& e, const juce::MouseWheelDetails& w)
{
    if (e.mods.isCommandDown() || e.mods.isCtrlDown())
    {
        const double anchor = xToBeat (e.x);
        pxPerBeat = juce::jlimit (2.0, 200.0, pxPerBeat * (w.deltaY > 0 ? 1.2 : 1 / 1.2));
        scrollBeats = juce::jmax (0.0, anchor - (e.x - headerW) / pxPerBeat);
    }
    else if (e.mods.isShiftDown() || std::abs (w.deltaX) > std::abs (w.deltaY))
        scrollBeats = juce::jmax (0.0, scrollBeats - (w.deltaX != 0 ? w.deltaX : w.deltaY) * 400.0 / pxPerBeat);
    else
    {
        const int maxY = juce::jmax (0, (int) ctx.project().tracks.size() * laneH - (getHeight() - rulerH));
        scrollY = juce::jlimit (0, maxY, scrollY - (int) (w.deltaY * 200));
    }
    repaint();
}

void ArrangementView::deleteSelected()
{
    if (ctx.selection.where != Selection::Where::arrangement) return;
    auto sel = ctx.selection;
    ctx.ctl.edit ("Delete clip", [sel] (Project& p)
    {
        if (auto* t = p.findTrack (sel.trackId))
            t->arrangement.erase (std::remove_if (t->arrangement.begin(), t->arrangement.end(),
                                                  [&] (auto& pl) { return pl.clip->id == sel.clipId; }), t->arrangement.end());
    });
    ctx.select (sel.trackId);
}

bool ArrangementView::keyPressed (const juce::KeyPress& k)
{
    if (k == juce::KeyPress::deleteKey || k == juce::KeyPress::backspaceKey) { deleteSelected(); return true; }
    return false;
}

bool ArrangementView::isInterestedInFileDrag (const juce::StringArray& files)
{
    for (auto& f : files) if (AppContext::isAudioFile (f)) return true;
    return false;
}

void ArrangementView::filesDropped (const juce::StringArray& files, int x, int y)
{
    for (auto& f : files) if (AppContext::isAudioFile (f)) dropAudio (juce::File (f), { x, y });
}

bool ArrangementView::isInterestedInDragSource (const SourceDetails& d) { return d.description == "TesseraFile"; }

void ArrangementView::itemDropped (const SourceDetails& d)
{
    if (ctx.browserSelectedFile) dropAudio (ctx.browserSelectedFile(), d.localPosition);
}

void ArrangementView::dropAudio (const juce::File& f, juce::Point<int> pos)
{
    const auto& p = ctx.project();
    auto clip = AppContext::audioClipFromFile (f, p.tempo, paletteColour ((int) p.tracks.size()));
    if (clip == nullptr) return;
    clip->looping = false;
    const double at = snap (xToBeat (pos.x));
    const int lane = laneAt (pos.y);
    if (lane >= 0 && lane < (int) p.tracks.size() && p.tracks[(size_t) lane].kind == TrackKind::audio)
    {
        clip->colour = p.tracks[(size_t) lane].colour;
        ctx.ctl.edit ("Add audio clip", [id = p.tracks[(size_t) lane].id, clip, at] (Project& pr)
        { if (auto* t = pr.findTrack (id)) t->arrangement.push_back ({ clip, at, clip->lengthBeats }); });
    }
    else
    {
        const int n = (int) p.tracks.size();
        ctx.ctl.edit ("Add audio clip", [clip, at, n] (Project& pr)
        {
            auto t = makeTrack (TrackKind::audio, clip->name, n);
            clip->colour = t.colour;
            t.arrangement.push_back ({ clip, at, clip->lengthBeats });
            pr.tracks.push_back (t);
        });
    }
}

} // namespace tessera
