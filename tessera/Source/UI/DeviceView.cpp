#include "Views.h"

namespace tessera
{

// One device panel: a titled box of rotary knobs bound to a parameter map.
struct DeviceView::Panel : public juce::Component
{
    using Getter = std::function<std::map<juce::String, float> (const Track&)>;
    using Setter = std::function<void (Track&, const juce::String&, float)>;

    Panel (AppContext& c, juce::String trackId, juce::String t, const std::vector<ParamDef>& d, Getter g, Setter s)
        : ctx (c), track (std::move (trackId)), title (std::move (t)), defs (d), get (std::move (g)), set (std::move (s))
    {
        for (auto& def : defs)
        {
            auto* k = knobs.add (new juce::Slider (juce::Slider::RotaryHorizontalVerticalDrag, juce::Slider::TextBoxBelow));
            auto* l = labels.add (new juce::Label ({}, def.label));
            l->setJustificationType (juce::Justification::centred);
            l->setFont (theme::font (10.5f));
            l->setColour (juce::Label::textColourId, theme::textDim);
            k->setRange (def.min, def.max, (def.max - def.min) > 50 ? 1.0 : 0.001);
            if (def.skewCentre > 0) k->setSkewFactorFromMidPoint (def.skewCentre);
            k->setTextValueSuffix (def.suffix);
            k->setNumDecimalPlacesToDisplay ((def.max - def.min) > 50 ? 0 : 2);
            k->setTextBoxStyle (juce::Slider::TextBoxBelow, false, 64, 15);
            k->setDoubleClickReturnValue (true, def.def);
            const juce::String key = def.key;
            k->onDragStart = [this] { ctx.ctl.beginGesture (title); };
            k->onValueChange = [this, k, key]
            {
                const float v = (float) k->getValue();
                auto setFn = set;
                ctx.ctl.edit (title, [id = track, key, v, setFn] (Project& p) { if (auto* t = p.findTrack (id)) setFn (*t, key, v); }, ! k->isMouseButtonDown());
            };
            addAndMakeVisible (k);
            addAndMakeVisible (l);
        }
        refresh();
    }

    void refresh()
    {
        auto* t = ctx.project().findTrack (track);
        if (t == nullptr) return;
        auto vals = get (*t);
        for (size_t i = 0; i < defs.size(); ++i)
            if (! knobs[(int) i]->isMouseButtonDown())
                knobs[(int) i]->setValue (paramValue (vals, defs, defs[i].key), juce::dontSendNotification);
    }

    int rows() const { return defs.size() <= 4 ? 1 : 2; }
    int preferredWidth() const { return juce::jmax (150, ((int) defs.size() + rows() - 1) / rows() * 72 + 16) + extraWidth; }

    void paint (juce::Graphics& g) override
    {
        g.setColour (theme::panelHi);
        g.fillRoundedRectangle (getLocalBounds().toFloat().reduced (2), 4);
        g.setColour (enabled ? theme::text : theme::textDim);
        g.setFont (theme::font (12.0f, true));
        g.drawText (title, 10, 4, getWidth() - 60, 18, juce::Justification::centredLeft);
    }

    void resized() override
    {
        auto r = getLocalBounds().reduced (6).withTrimmedTop (22);
        if (extraWidth > 0) r.removeFromLeft (extraWidth);
        const int nr = rows();
        const int cols = juce::jmax (1, ((int) defs.size() + nr - 1) / nr);
        const int w = juce::jmin (72, r.getWidth() / cols);
        const int h = juce::jmin (84, r.getHeight() / nr);
        for (int i = 0; i < knobs.size(); ++i)
        {
            auto cell = juce::Rectangle<int> (r.getX() + (i / nr) * w, r.getY() + (i % nr) * h, w, h);
            labels[i]->setBounds (cell.removeFromTop (14));
            knobs[i]->setBounds (cell);
        }
    }

    AppContext& ctx;
    juce::String track, title;
    std::vector<ParamDef> defs;
    Getter get;
    Setter set;
    juce::OwnedArray<juce::Slider> knobs;
    juce::OwnedArray<juce::Label> labels;
    std::unique_ptr<juce::TextButton> onOff, remove, left;
    bool enabled = true;
    int extraWidth = 0;
};

DeviceView::DeviceView (AppContext& c) : ctx (c)
{
    addAndMakeVisible (viewport);
    viewport.setViewedComponent (&content, false);
    viewport.setScrollBarsShown (false, true);
    content.addAndMakeVisible (addFx);
    content.addAndMakeVisible (instType);
    addFx.onClick = [this]
    {
        juce::PopupMenu m;
        for (int i = 0; i < 5; ++i) m.addItem (i + 1, effectTypeName ((EffectType) i));
        m.showMenuAsync (juce::PopupMenu::Options().withTargetComponent (&addFx), [this] (int r)
        {
            if (r <= 0) return;
            const auto type = (EffectType) (r - 1);
            ctx.ctl.edit ("Add " + effectTypeName (type), [id = ctx.selection.trackId, type] (Project& p)
            { if (auto* t = p.findTrack (id)) t->effects.push_back (makeEffect (type)); });
        });
    };
    instType.onClick = [this]
    {
        juce::PopupMenu m;
        m.addItem (1, "Poly Synth");
        m.addItem (2, "Drum Sampler");
        m.showMenuAsync (juce::PopupMenu::Options().withTargetComponent (&instType), [this] (int r)
        {
            if (r <= 0) return;
            const auto type = r == 1 ? InstrumentType::synth : InstrumentType::drums;
            ctx.ctl.edit ("Change instrument", [id = ctx.selection.trackId, type] (Project& p)
            {
                if (auto* t = p.findTrack (id); t && t->instrument.type != type)
                {
                    t->instrument.type = type;
                    t->instrument.params = defaultsFor (type == InstrumentType::synth ? synthParams() : drumParams());
                }
            });
        });
    };
    content.addMouseListener (this, false);
    content.overlay = [this] (juce::Graphics& g)
    {
        const auto* t = ctx.project().findTrack (ctx.selection.trackId);
        if (t == nullptr || t->instrument.type != InstrumentType::drums || padArea.isEmpty()) return;
        for (int pad = 0; pad < DrumSampler::numPads; ++pad)
        {
            auto r = padRect (pad);
            const bool custom = t->instrument.padSamples[(size_t) pad].isNotEmpty();
            g.setColour (pad == heldPad ? theme::accent : custom ? theme::cell.brighter (0.25f) : theme::cell);
            g.fillRoundedRectangle (r.toFloat(), 3);
            g.setColour (pad == heldPad ? theme::bg : theme::text);
            g.setFont (theme::font (9.5f));
            const auto name = custom ? juce::File (t->instrument.padSamples[(size_t) pad]).getFileNameWithoutExtension() : DrumSampler::padName (pad);
            g.drawFittedText (name, r.reduced (2), juce::Justification::centred, 2);
        }
    };
    ctx.ctl.addChangeListener (this);
    ctx.selectionChanged.addChangeListener (this);
    rebuild();
}

DeviceView::~DeviceView()
{
    ctx.ctl.removeChangeListener (this);
    ctx.selectionChanged.removeChangeListener (this);
}

void DeviceView::changeListenerCallback (juce::ChangeBroadcaster*)
{
    const auto* t = ctx.project().findTrack (ctx.selection.trackId);
    juce::String key;
    if (t)
    {
        key << t->id << ":" << (int) t->instrument.type << ":" << (int) t->kind;
        for (auto& e : t->effects) key << ":" << e.id << (e.enabled ? "1" : "0");
    }
    if (key != builtFor) rebuild();
    else for (auto* p : panels) p->refresh();
    repaint();
}

void DeviceView::rebuild()
{
    panels.clear();
    const auto* t = ctx.project().findTrack (ctx.selection.trackId);
    builtFor = {};
    if (t)
    {
        builtFor << t->id << ":" << (int) t->instrument.type << ":" << (int) t->kind;
        for (auto& e : t->effects) builtFor << ":" << e.id << (e.enabled ? "1" : "0");
    }
    instType.setVisible (t && t->kind == TrackKind::midi);
    addFx.setVisible (t != nullptr);
    if (t == nullptr) { resized(); return; }

    if (t->kind == TrackKind::midi && t->instrument.type == InstrumentType::synth)
        content.addAndMakeVisible (panels.add (new Panel (ctx, t->id, "Poly Synth", synthParams(),
            [] (const Track& tr) { return tr.instrument.params; },
            [] (Track& tr, const juce::String& k, float v) { tr.instrument.params[k] = v; })));
    if (t->kind == TrackKind::midi && t->instrument.type == InstrumentType::drums)
    {
        auto* p = panels.add (new Panel (ctx, t->id, "Drum Sampler", drumParams(),
            [] (const Track& tr) { return tr.instrument.params; },
            [] (Track& tr, const juce::String& k, float v) { tr.instrument.params[k] = v; }));
        p->extraWidth = 4 * 46 + 8;   // room for the 4x4 pad grid (painted by Content::overlay)
        p->setInterceptsMouseClicks (false, true);   // clicks on pads reach DeviceView
        content.addAndMakeVisible (p);
    }
    for (size_t i = 0; i < t->effects.size(); ++i)
    {
        const auto& e = t->effects[i];
        const juce::String fxId = e.id;
        auto* p = panels.add (new Panel (ctx, t->id, effectTypeName (e.type), effectParams (e.type),
            [fxId] (const Track& tr) { for (auto& x : tr.effects) if (x.id == fxId) return x.params; return std::map<juce::String, float>(); },
            [fxId] (Track& tr, const juce::String& k, float v) { for (auto& x : tr.effects) if (x.id == fxId) x.params[k] = v; }));
        p->enabled = e.enabled;
        p->onOff = std::make_unique<juce::TextButton> (e.enabled ? "On" : "Off");
        p->onOff->setToggleState (e.enabled, juce::dontSendNotification);
        p->onOff->onClick = [this, fxId]
        {
            ctx.ctl.edit ("Toggle effect", [id = ctx.selection.trackId, fxId] (Project& pr)
            { if (auto* tr = pr.findTrack (id)) for (auto& x : tr->effects) if (x.id == fxId) x.enabled = ! x.enabled; });
        };
        p->remove = std::make_unique<juce::TextButton> ("x");
        p->remove->setTooltip ("Remove effect");
        p->remove->onClick = [this, fxId]
        {
            ctx.ctl.edit ("Remove effect", [id = ctx.selection.trackId, fxId] (Project& pr)
            {
                if (auto* tr = pr.findTrack (id))
                    tr->effects.erase (std::remove_if (tr->effects.begin(), tr->effects.end(), [&] (auto& x) { return x.id == fxId; }), tr->effects.end());
            });
        };
        if (i > 0)
        {
            p->left = std::make_unique<juce::TextButton> ("<");
            p->left->setTooltip ("Move earlier in the chain");
            p->left->onClick = [this, fxId]
            {
                ctx.ctl.edit ("Reorder effects", [id = ctx.selection.trackId, fxId] (Project& pr)
                {
                    if (auto* tr = pr.findTrack (id))
                        for (size_t k = 1; k < tr->effects.size(); ++k)
                            if (tr->effects[k].id == fxId) { std::swap (tr->effects[k], tr->effects[k - 1]); return; }
                });
            };
            p->addAndMakeVisible (*p->left);
        }
        p->addAndMakeVisible (*p->onOff);
        p->addAndMakeVisible (*p->remove);
        for (auto* k : p->knobs) k->setEnabled (e.enabled);
        content.addAndMakeVisible (p);
    }
    resized();
}

void DeviceView::resized()
{
    viewport.setBounds (getLocalBounds().withTrimmedTop (24));
    int x = 6;
    const int h = juce::jmax (120, viewport.getHeight() - (viewport.isHorizontalScrollBarShown() ? 10 : 2));
    instType.setBounds (x, 4, 92, 22);
    addFx.setBounds (x, 30, 92, 22);
    x += 100;
    padArea = {};
    for (auto* p : panels)
    {
        const int w = p->preferredWidth();
        p->setBounds (x, 0, w, h);
        if (p->onOff) p->onOff->setBounds (w - 64, 4, 34, 18);
        if (p->remove) p->remove->setBounds (w - 28, 4, 20, 18);
        if (p->left) p->left->setBounds (w - 88, 4, 20, 18);
        if (p->extraWidth > 0) padArea = juce::Rectangle<int> (x + 10, 28, p->extraWidth - 8, h - 36);
        x += w + 4;
    }
    content.setSize (juce::jmax (x + 6, viewport.getWidth()), h);
}

juce::Rectangle<int> DeviceView::padRect (int pad) const
{
    // pads laid out bottom-left = pad 0, like a hardware drum controller
    const int col = pad % 4, row = 3 - pad / 4;
    const int w = padArea.getWidth() / 4, h = padArea.getHeight() / 4;
    return juce::Rectangle<int> (padArea.getX() + col * w, padArea.getY() + row * h, w, h).reduced (2);
}

void DeviceView::paint (juce::Graphics& g)
{
    g.fillAll (theme::panel);
    g.setColour (theme::textDim);
    g.setFont (theme::font (11.0f, true));
    const auto* t = ctx.project().findTrack (ctx.selection.trackId);
    g.drawText (t ? "DEVICES  -  " + t->name.toUpperCase() : "DEVICES  -  select a track", 8, 2, getWidth() - 16, 20, juce::Justification::centredLeft);
}


bool DeviceView::isInterestedInFileDrag (const juce::StringArray& files)
{
    for (auto& f : files) if (AppContext::isAudioFile (f)) return true;
    return false;
}

void DeviceView::filesDropped (const juce::StringArray& files, int x, int y)
{
    const auto* t = ctx.project().findTrack (ctx.selection.trackId);
    if (t == nullptr || t->instrument.type != InstrumentType::drums || files.isEmpty()) return;
    auto p = content.getLocalPoint (this, juce::Point<int> (x, y));
    for (int pad = 0; pad < DrumSampler::numPads; ++pad)
        if (padRect (pad).contains (p))
        {
            const auto path = files[0];
            ctx.ctl.edit ("Load pad sample", [id = t->id, pad, path] (Project& pr) { if (auto* tr = pr.findTrack (id)) tr->instrument.padSamples[(size_t) pad] = path; });
            return;
        }
}

void DeviceView::mouseDown (const juce::MouseEvent& e)
{
    const auto* t = ctx.project().findTrack (ctx.selection.trackId);
    if (t == nullptr || t->instrument.type != InstrumentType::drums) return;
    auto p = e.getEventRelativeTo (&content).getPosition();
    for (int pad = 0; pad < DrumSampler::numPads; ++pad)
        if (padRect (pad).contains (p))
        {
            if (e.mods.isPopupMenu())
            {
                juce::PopupMenu m;
                m.addItem (1, "Clear sample (use built-in)", t->instrument.padSamples[(size_t) pad].isNotEmpty());
                m.showMenuAsync ({}, [this, id = t->id, pad] (int r)
                {
                    if (r == 1) ctx.ctl.edit ("Clear pad", [id, pad] (Project& pr) { if (auto* tr = pr.findTrack (id)) tr->instrument.padSamples[(size_t) pad] = {}; });
                });
                return;
            }
            heldPad = pad;
            content.repaint();
            ctx.engine.noteOn (ctx.project().trackIndex (t->id), DrumSampler::baseNote + pad, 0.9f);
            return;
        }
}

void DeviceView::mouseUp (const juce::MouseEvent&)
{
    if (heldPad >= 0) ctx.engine.noteOff (ctx.project().trackIndex (ctx.selection.trackId), DrumSampler::baseNote + heldPad);
    heldPad = -1;
    content.repaint();
}

} // namespace tessera
