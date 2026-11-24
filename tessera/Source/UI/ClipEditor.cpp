#include "Views.h"

namespace tessera
{

static constexpr int controlsH = 32, keysW = 44;
static const char* const noteNames[] = { "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B" };
static bool isBlack (int pitch) { const int n = pitch % 12; return n == 1 || n == 3 || n == 6 || n == 8 || n == 10; }

ClipEditor::ClipEditor (AppContext& c) : ctx (c)
{
    formats.registerBasicFormats();
    setWantsKeyboardFocus (true);
    addAndMakeVisible (title);
    title.setFont (theme::font (13.0f, true));

    addAndMakeVisible (gridBox);
    gridBox.addItemList ({ "Grid 1/4", "Grid 1/8", "Grid 1/16", "Grid 1/32" }, 1);
    gridBox.setSelectedItemIndex (2);
    gridBox.onChange = [this] { repaint(); };

    addAndMakeVisible (lengthSlider);
    lengthSlider.setRange (0.25, 256.0, 0.25);
    lengthSlider.setTextValueSuffix (" beats");
    lengthSlider.setTextBoxStyle (juce::Slider::TextBoxLeft, false, 80, 22);
    lengthSlider.onValueChange = [this]
    {
        const double v = lengthSlider.getValue();
        if (auto c = ctx.selectedClip(); c && std::abs (c->lengthBeats - v) > 1e-9)
            ctx.updateSelectedClip ("Clip length", [v] (Clip& cl) { cl.lengthBeats = v; });
    };
    addAndMakeVisible (loopToggle);
    loopToggle.onClick = [this] { const bool on = loopToggle.getToggleState(); ctx.updateSelectedClip ("Loop", [on] (Clip& cl) { cl.looping = on; }); };
    addAndMakeVisible (quantizeBtn);
    quantizeBtn.setTooltip ("Snap note starts to the grid");
    quantizeBtn.onClick = [this]
    {
        const double g = gridBeats();
        ctx.updateSelectedClip ("Quantize", [g] (Clip& cl)
        {
            for (auto& n : cl.notes) n.start = std::round (n.start / g) * g;
            std::sort (cl.notes.begin(), cl.notes.end(), [] (auto& a, auto& b) { return a.start < b.start; });
        });
    };
    addAndMakeVisible (dupBtn);
    dupBtn.setTooltip ("Double the clip length and copy its notes");
    dupBtn.onClick = [this]
    {
        ctx.updateSelectedClip ("Duplicate loop", [] (Clip& cl)
        {
            const auto L = cl.lengthBeats;
            const auto copy = cl.notes;
            for (auto n : copy) { n.start += L; cl.notes.push_back (n); }
            cl.lengthBeats = L * 2;
        });
    };
    addAndMakeVisible (warpToggle);
    warpToggle.setTooltip ("Warp: follow project tempo by re-pitching (speed changes pitch)");
    warpToggle.onClick = [this] { const bool on = warpToggle.getToggleState(); ctx.updateSelectedClip ("Warp", [on] (Clip& cl) { cl.warp = on; }); };
    addAndMakeVisible (sourceTempo);
    sourceTempo.setRange (20.0, 300.0, 0.01);
    sourceTempo.setTextValueSuffix (" BPM");
    sourceTempo.setTextBoxStyle (juce::Slider::TextBoxLeft, false, 80, 22);
    sourceTempo.setTooltip ("Original tempo of the audio file");
    sourceTempo.onValueChange = [this]
    {
        const double v = sourceTempo.getValue();
        if (auto c = ctx.selectedClip(); c && std::abs (c->sourceTempo - v) > 1e-9)
            ctx.updateSelectedClip ("Source tempo", [v] (Clip& cl) { cl.sourceTempo = v; });
    };
    addAndMakeVisible (gainSlider);
    gainSlider.setRange (-36.0, 12.0, 0.1);
    gainSlider.setTextValueSuffix (" dB");
    gainSlider.onDragStart = [this] { ctx.ctl.beginGesture ("Clip gain"); };
    gainSlider.onValueChange = [this]
    {
        const float v = (float) gainSlider.getValue();
        if (auto c = ctx.selectedClip(); c && std::abs (c->gainDb - v) > 1e-4f)
            ctx.updateSelectedClip ("Clip gain", [v] (Clip& cl) { cl.gainDb = v; }, ! gainSlider.isMouseButtonDown());
    };

    ctx.ctl.addChangeListener (this);
    ctx.selectionChanged.addChangeListener (this);
    refreshControls();
    startTimerHz (20);
}

ClipEditor::~ClipEditor()
{
    ctx.ctl.removeChangeListener (this);
    ctx.selectionChanged.removeChangeListener (this);
}

void ClipEditor::changeListenerCallback (juce::ChangeBroadcaster* b)
{
    if (b == &ctx.selectionChanged)
    {
        selectedNote = -1;
        if (auto c = ctx.selectedClip(); c && ! c->notes.empty())
        {   // scroll so the clip's notes are in view
            int lo = 127, hi = 0;
            for (auto& n : c->notes) { lo = juce::jmin (lo, n.pitch); hi = juce::jmax (hi, n.pitch); }
            const int visible = juce::jmax (12, (int) (gridArea().getHeight() / noteH));
            topPitch = juce::jlimit (visible - 1, 127, (lo + hi) / 2 + visible / 2);
        }
    }
    refreshControls();
    repaint();
}

void ClipEditor::refreshControls()
{
    auto c = ctx.selectedClip();
    const bool midi = c && c->kind == ClipKind::midi;
    const bool audio = c && c->kind == ClipKind::audio;
    for (auto* comp : std::initializer_list<juce::Component*> { &gridBox, &quantizeBtn, &dupBtn }) comp->setVisible (midi);
    for (auto* comp : std::initializer_list<juce::Component*> { &warpToggle, &sourceTempo, &gainSlider }) comp->setVisible (audio);
    lengthSlider.setVisible (c != nullptr);
    loopToggle.setVisible (c != nullptr);
    title.setText (c ? c->name + (midi ? "  -  MIDI" : "  -  Audio") : "No clip selected", juce::dontSendNotification);
    if (c)
    {
        lengthSlider.setValue (c->lengthBeats, juce::dontSendNotification);
        loopToggle.setToggleState (c->looping, juce::dontSendNotification);
        warpToggle.setToggleState (c->warp, juce::dontSendNotification);
        sourceTempo.setValue (c->sourceTempo, juce::dontSendNotification);
        if (! gainSlider.isMouseButtonDown()) gainSlider.setValue (c->gainDb, juce::dontSendNotification);
        if (audio && c->audioFile != thumbFile) loadThumbnail();
    }
}

void ClipEditor::loadThumbnail()
{
    auto c = ctx.selectedClip();
    thumbFile = c ? c->audioFile : juce::String();
    thumb.setSource (thumbFile.isNotEmpty() ? new juce::FileInputSource (juce::File (thumbFile)) : nullptr);
}

void ClipEditor::resized()
{
    auto r = getLocalBounds().removeFromTop (controlsH).reduced (6, 4);
    title.setBounds (r.removeFromLeft (220));
    lengthSlider.setBounds (r.removeFromLeft (170));
    r.removeFromLeft (6);
    loopToggle.setBounds (r.removeFromLeft (60));
    gridBox.setBounds (r.removeFromLeft (100));
    r.removeFromLeft (6);
    quantizeBtn.setBounds (r.removeFromLeft (70));
    r.removeFromLeft (6);
    dupBtn.setBounds (r.removeFromLeft (36));
    auto ar = getLocalBounds().removeFromTop (controlsH).reduced (6, 4);
    ar.removeFromLeft (220 + 170 + 6 + 60);
    warpToggle.setBounds (ar.removeFromLeft (64));
    sourceTempo.setBounds (ar.removeFromLeft (170));
    ar.removeFromLeft (6);
    gainSlider.setBounds (ar.removeFromLeft (200));
}

juce::Rectangle<int> ClipEditor::gridArea() const { return getLocalBounds().withTrimmedTop (controlsH).withTrimmedLeft (keysW); }
double ClipEditor::gridBeats() const { return 1.0 / std::pow (2.0, gridBox.getSelectedItemIndex()); }

double ClipEditor::xToBeat (int x) const
{
    auto c = ctx.selectedClip();
    const auto g = gridArea();
    const double L = c ? c->lengthBeats : 4.0;
    return (x - g.getX()) / (double) juce::jmax (1, g.getWidth()) * L;
}

int ClipEditor::beatToX (double b) const
{
    auto c = ctx.selectedClip();
    const auto g = gridArea();
    const double L = c ? c->lengthBeats : 4.0;
    return g.getX() + (int) std::round (b / L * g.getWidth());
}

int ClipEditor::pitchToY (int pitch) const { return gridArea().getY() + (int) ((topPitch - pitch) * noteH); }
int ClipEditor::yToPitch (int y) const { return juce::jlimit (0, 127, topPitch - (int) std::floor ((y - gridArea().getY()) / noteH)); }

int ClipEditor::noteAt (juce::Point<int> p, bool& rightEdge) const
{
    auto c = ctx.selectedClip();
    if (c == nullptr || c->kind != ClipKind::midi) return -1;
    for (int i = (int) c->notes.size() - 1; i >= 0; --i)
    {
        const auto& n = c->notes[(size_t) i];
        auto r = juce::Rectangle<int>::leftTopRightBottom (beatToX (n.start), pitchToY (n.pitch), beatToX (n.start + n.length), pitchToY (n.pitch) + (int) noteH);
        if (r.expanded (0, 0).contains (p)) { rightEdge = p.x >= r.getRight() - 5; return i; }
    }
    return -1;
}

void ClipEditor::paint (juce::Graphics& g)
{
    g.fillAll (theme::panel);
    g.setColour (theme::line);
    g.drawHorizontalLine (controlsH - 1, 0, (float) getWidth());
    auto c = ctx.selectedClip();
    const auto area = gridArea();
    if (c == nullptr)
    {
        g.setColour (theme::textDim);
        g.setFont (theme::font (13.0f));
        g.drawText ("Select a clip to edit it. Double-click an empty MIDI slot or lane to create one.", area, juce::Justification::centred);
        return;
    }
    if (c->kind == ClipKind::audio)
    {
        auto r = getLocalBounds().withTrimmedTop (controlsH).reduced (8);
        g.setColour (theme::bg);
        g.fillRect (r);
        g.setColour (c->colour);
        if (thumb.getTotalLength() > 0)
        {
            // show the portion of the file covered by the clip length
            const double secs = c->lengthBeats * 60.0 / (c->warp ? c->sourceTempo : ctx.project().tempo);
            thumb.drawChannels (g, r, 0.0, juce::jmin (secs, thumb.getTotalLength()), 1.0f);
        }
        else
        {
            g.setColour (theme::record);
            g.drawText ("Audio file not found: " + c->audioFile, r, juce::Justification::centred);
        }
        g.setColour (theme::textDim);
        g.setFont (theme::font (11.0f));
        g.drawText (c->audioFile, r.reduced (6).removeFromBottom (16), juce::Justification::bottomLeft, true);
        return;
    }

    // ---- piano roll
    g.setColour (theme::bg);
    g.fillRect (area);
    g.saveState();
    g.reduceClipRegion (area.withLeft (0));
    for (int pitch = topPitch; pitch >= 0; --pitch)
    {
        const int y = pitchToY (pitch);
        if (y > getHeight()) break;
        if (isBlack (pitch)) { g.setColour (theme::panel.withAlpha (0.6f)); g.fillRect (area.getX(), y, area.getWidth(), (int) noteH); }
        // keyboard
        auto key = juce::Rectangle<int> (0, y, keysW - 2, (int) noteH);
        g.setColour (isBlack (pitch) ? theme::bg : theme::textDim.withAlpha (pitch == previewPitch ? 1.0f : 0.55f));
        g.fillRect (key.reduced (0, 0).withTrimmedBottom (1));
        if (pitch % 12 == 0)
        {
            g.setColour (theme::bg);
            g.setFont (theme::font (9.5f));
            g.drawText (noteNames[0] + juce::String (pitch / 12 - 2), key.reduced (3, 0), juce::Justification::centredRight);
            g.setColour (theme::line);
            g.drawHorizontalLine (y + (int) noteH, (float) area.getX(), (float) area.getRight());
        }
    }
    const double grid = gridBeats();
    for (double b = 0; b <= c->lengthBeats + 1e-9; b += grid)
    {
        const bool beat = std::abs (b - std::round (b)) < 1e-9;
        const bool bar = beat && ((int) std::round (b)) % juce::jmax (1, ctx.project().beatsPerBar) == 0;
        g.setColour (bar ? theme::line.brighter (0.3f) : beat ? theme::line : theme::line.withAlpha (0.35f));
        g.drawVerticalLine (beatToX (b), (float) area.getY(), (float) area.getBottom());
    }
    for (int i = 0; i < (int) c->notes.size(); ++i)
    {
        const auto& n = c->notes[(size_t) i];
        auto r = juce::Rectangle<int>::leftTopRightBottom (beatToX (n.start), pitchToY (n.pitch), juce::jmax (beatToX (n.start) + 3, beatToX (n.start + n.length)), pitchToY (n.pitch) + (int) noteH);
        g.setColour (c->colour.withMultipliedBrightness (0.6f + 0.6f * n.velocity));
        g.fillRect (r.reduced (0, 1));
        g.setColour (i == selectedNote ? theme::text : juce::Colours::black.withAlpha (0.5f));
        g.drawRect (r.reduced (0, 1), i == selectedNote ? 2 : 1);
    }
    // playhead within the clip when it is playing in the session
    const int ti = ctx.project().trackIndex (ctx.selection.trackId);
    if (auto* rt = ctx.engine.runtimeFor (ti); rt && ctx.selection.where == Selection::Where::slot && rt->playingSlot.load() == ctx.selection.slot)
    {
        g.setColour (theme::play);
        g.drawVerticalLine (beatToX (rt->clipPhase.load() * c->lengthBeats), (float) area.getY(), (float) area.getBottom());
    }
    g.restoreState();
    g.setColour (theme::textDim);
    g.setFont (theme::font (10.5f));
    g.drawText ("Click: add  |  Drag: move  |  Drag edge: resize  |  Double-click: delete  |  Shift-drag: velocity  |  Wheel: scroll",
                area.reduced (6, 3), juce::Justification::bottomRight);
}

void ClipEditor::mouseDown (const juce::MouseEvent& e)
{
    grabKeyboardFocus();
    auto c = ctx.selectedClip();
    if (c == nullptr || c->kind != ClipKind::midi || e.y < controlsH) return;
    const int ti = ctx.project().trackIndex (ctx.selection.trackId);
    if (e.x < keysW)
    {
        previewPitch = yToPitch (e.y);
        ctx.engine.noteOn (ti, previewPitch, 0.8f);
        repaint();
        return;
    }
    bool edge = false;
    int idx = noteAt (e.getPosition(), edge);
    ctx.ctl.beginGesture ("Edit notes");
    if (idx < 0)
    {
        const double g = gridBeats();
        Note n { yToPitch (e.y), std::floor (xToBeat (e.x) / g) * g, g, 0.8f };
        if (n.start >= c->lengthBeats) return;
        ctx.updateSelectedClip ("Add note", [n] (Clip& cl)
        {
            cl.notes.push_back (n);
            std::sort (cl.notes.begin(), cl.notes.end(), [] (auto& a, auto& b) { return a.start < b.start; });
        }, false);
        auto updated = ctx.selectedClip();
        for (int i = 0; i < (int) updated->notes.size(); ++i)
            if (updated->notes[(size_t) i] == n) idx = i;
        edge = false;
        ctx.engine.noteOn (ti, n.pitch, n.velocity);
        previewPitch = n.pitch;
    }
    selectedNote = dragNote = idx;
    dragResize = edge;
    dragOriginal = ctx.selectedClip()->notes;
    dragBeatOffset = xToBeat (e.x) - dragOriginal[(size_t) idx].start;
    repaint();
}

void ClipEditor::mouseDrag (const juce::MouseEvent& e)
{
    if (dragNote < 0 || dragNote >= (int) dragOriginal.size()) return;
    const double g = gridBeats();
    auto orig = dragOriginal[(size_t) dragNote];
    auto clip = ctx.selectedClip();
    if (clip == nullptr) return;
    Note n = orig;
    if (e.mods.isShiftDown())
        n.velocity = juce::jlimit (0.05f, 1.0f, orig.velocity - e.getDistanceFromDragStartY() / 150.0f);
    else if (dragResize)
        n.length = juce::jmax (g, std::round ((xToBeat (e.x) - orig.start) / g) * g);
    else
    {
        n.start = juce::jlimit (0.0, clip->lengthBeats - g, std::round ((xToBeat (e.x) - dragBeatOffset) / g) * g);
        n.pitch = yToPitch (e.y);
    }
    const int idx = dragNote;
    auto base = dragOriginal;
    ctx.updateSelectedClip ("Edit notes", [base, idx, n] (Clip& cl) { cl.notes = base; cl.notes[(size_t) idx] = n; }, false);
}

void ClipEditor::mouseUp (const juce::MouseEvent&)
{
    const int ti = ctx.project().trackIndex (ctx.selection.trackId);
    if (previewPitch >= 0) ctx.engine.noteOff (ti, previewPitch);
    previewPitch = -1;
    if (dragNote >= 0)
        ctx.updateSelectedClip ("Edit notes", [] (Clip& cl)
        { std::stable_sort (cl.notes.begin(), cl.notes.end(), [] (auto& a, auto& b) { return a.start < b.start; }); }, false);
    dragNote = -1;
    repaint();
}

void ClipEditor::mouseDoubleClick (const juce::MouseEvent& e)
{
    bool edge;
    const int idx = noteAt (e.getPosition(), edge);
    if (idx < 0) return;
    ctx.updateSelectedClip ("Delete note", [idx] (Clip& cl) { if (idx < (int) cl.notes.size()) cl.notes.erase (cl.notes.begin() + idx); });
    selectedNote = -1;
}

void ClipEditor::mouseWheelMove (const juce::MouseEvent& e, const juce::MouseWheelDetails& w)
{
    if (e.mods.isCommandDown() || e.mods.isCtrlDown()) noteH = juce::jlimit (5.0f, 24.0f, noteH + (w.deltaY > 0 ? 1.0f : -1.0f));
    else topPitch = juce::jlimit (12, 127, topPitch + (w.deltaY > 0 ? 2 : -2));
    repaint();
}

bool ClipEditor::keyPressed (const juce::KeyPress& k)
{
    if ((k == juce::KeyPress::deleteKey || k == juce::KeyPress::backspaceKey) && selectedNote >= 0)
    {
        const int idx = selectedNote;
        ctx.updateSelectedClip ("Delete note", [idx] (Clip& cl) { if (idx < (int) cl.notes.size()) cl.notes.erase (cl.notes.begin() + idx); });
        selectedNote = -1;
        return true;
    }
    return false;
}

} // namespace tessera
