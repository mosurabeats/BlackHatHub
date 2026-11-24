#include "Views.h"

namespace tessera
{

TransportBar::TransportBar (AppContext& c) : ctx (c)
{
    for (auto* b : { &playBtn, &stopBtn, &recBtn, &metroBtn, &loopBtn, &sessionBtn, &arrangeBtn, &undoBtn, &redoBtn, &exportBtn, &browserBtn })
        addAndMakeVisible (b);
    playBtn.setColour (juce::TextButton::buttonOnColourId, theme::play);
    recBtn.setColour (juce::TextButton::buttonOnColourId, theme::record);
    metroBtn.setClickingTogglesState (false);

    playBtn.onClick = [this] { ctx.engine.play(); };
    stopBtn.onClick = [this]
    {
        if (ctx.engine.isRecording()) ctx.engine.stopRecording (ctx.ctl);
        ctx.engine.stop();
    };
    recBtn.onClick = [this] { toggleRecord(); };
    metroBtn.onClick = [this] { ctx.ctl.edit ("Metronome", [] (Project& p) { p.metronome = ! p.metronome; }); };
    loopBtn.onClick = [this] { ctx.ctl.edit ("Loop", [] (Project& p) { p.loopEnabled = ! p.loopEnabled; }); };
    sessionBtn.onClick = [this] { setSessionView (true); if (onViewChange) onViewChange (true); };
    arrangeBtn.onClick = [this] { setSessionView (false); if (onViewChange) onViewChange (false); };
    undoBtn.onClick = [this] { ctx.ctl.undo(); };
    redoBtn.onClick = [this] { ctx.ctl.redo(); };
    exportBtn.onClick = [this] { if (onExport) onExport(); };
    browserBtn.onClick = [this] { if (onToggleBrowser) onToggleBrowser(); };

    addAndMakeVisible (tempo);
    tempo.setRange (20.0, 300.0, 0.5);
    tempo.setTextBoxStyle (juce::Slider::TextBoxLeft, false, 56, 24);
    tempo.setIncDecButtonsMode (juce::Slider::incDecButtonsDraggable_Vertical);
    tempo.onDragStart = [this] { ctx.ctl.beginGesture ("Tempo"); };
    tempo.onValueChange = [this]
    {
        const double v = tempo.getValue();
        if (std::abs (v - ctx.project().tempo) > 1e-6)
            ctx.ctl.edit ("Tempo", [v] (Project& p) { p.tempo = v; }, ! tempo.isMouseButtonDown());
    };
    addAndMakeVisible (tempoLabel);
    tempoLabel.setColour (juce::Label::textColourId, theme::textDim);

    addAndMakeVisible (quantize);
    quantize.addItemList ({ "Launch: None", "Launch: 1 Bar", "Launch: 2 Bars", "Launch: 4 Bars" }, 1);
    quantize.onChange = [this]
    {
        const int idx = quantize.getSelectedItemIndex();
        const int bars = idx == 0 ? 0 : idx == 1 ? 1 : idx == 2 ? 2 : 4;
        if (bars != ctx.project().launchQuantizeBars) ctx.ctl.edit ("Launch quantize", [bars] (Project& p) { p.launchQuantizeBars = bars; });
    };

    addAndMakeVisible (masterVol);
    masterVol.setRange (-60.0, 6.0, 0.1);
    masterVol.setDoubleClickReturnValue (true, 0.0);
    masterVol.onDragStart = [this] { ctx.ctl.beginGesture ("Master volume"); };
    masterVol.onValueChange = [this]
    {
        const float v = (float) masterVol.getValue();
        if (std::abs (v - ctx.project().masterVolumeDb) > 1e-4f) ctx.ctl.edit ("Master volume", [v] (Project& p) { p.masterVolumeDb = v; }, false);
    };

    addAndMakeVisible (position);
    position.setFont (theme::font (17.0f, true));
    position.setJustificationType (juce::Justification::centred);
    position.setColour (juce::Label::backgroundColourId, theme::bg);

    ctx.ctl.addChangeListener (this);
    refresh();
    setSessionView (true);
    startTimerHz (30);
}

TransportBar::~TransportBar() { ctx.ctl.removeChangeListener (this); }

void TransportBar::toggleRecord()
{
    if (ctx.engine.isRecording()) { ctx.engine.stopRecording (ctx.ctl); return; }
    juce::String err;
    bool armed = false;
    for (auto& t : ctx.project().tracks) armed = armed || t.arm;
    if (! armed)
    {
        juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::InfoIcon, "Nothing armed",
            "Arm a track (the R button on its mixer strip) before recording.");
        return;
    }
    if (! ctx.engine.startRecording (err))
        juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::WarningIcon, "Recording failed", err);
}

void TransportBar::setSessionView (bool s)
{
    sessionView = s;
    sessionBtn.setToggleState (s, juce::dontSendNotification);
    arrangeBtn.setToggleState (! s, juce::dontSendNotification);
}

void TransportBar::refresh()
{
    const auto& p = ctx.project();
    tempo.setValue (p.tempo, juce::dontSendNotification);
    masterVol.setValue (p.masterVolumeDb, juce::dontSendNotification);
    metroBtn.setToggleState (p.metronome, juce::dontSendNotification);
    loopBtn.setToggleState (p.loopEnabled, juce::dontSendNotification);
    const int q = p.launchQuantizeBars;
    quantize.setSelectedItemIndex (q == 0 ? 0 : q == 1 ? 1 : q == 2 ? 2 : 3, juce::dontSendNotification);
    undoBtn.setEnabled (ctx.ctl.canUndo());
    redoBtn.setEnabled (ctx.ctl.canRedo());
    undoBtn.setTooltip (ctx.ctl.canUndo() ? "Undo " + ctx.ctl.undoName() : juce::String());
}

void TransportBar::timerCallback()
{
    const double beat = ctx.engine.positionBeats();
    const int bpb = juce::jmax (1, ctx.project().beatsPerBar);
    const int bar = (int) std::floor (beat / bpb) + 1;
    const int b = (int) std::floor (std::fmod (beat, (double) bpb)) + 1;
    const int six = (int) std::floor (std::fmod (beat, 1.0) * 4.0) + 1;
    position.setText (juce::String (bar) + "." + juce::String (b) + "." + juce::String (six), juce::dontSendNotification);
    playBtn.setToggleState (ctx.engine.isPlaying(), juce::dontSendNotification);
    recBtn.setToggleState (ctx.engine.isRecording(), juce::dontSendNotification);
    repaint (getLocalBounds().removeFromRight (60));
}

void TransportBar::paint (juce::Graphics& g)
{
    g.fillAll (theme::panel);
    g.setColour (theme::line);
    g.drawHorizontalLine (getHeight() - 1, 0, (float) getWidth());
    g.setColour (theme::accent);
    g.setFont (theme::font (18.0f, true));
    g.drawText ("TESSERA", 12, 0, 100, getHeight(), juce::Justification::centredLeft);
    auto meter = getLocalBounds().removeFromRight (56).reduced (8, 8);
    theme::drawMeter (g, meter.removeFromLeft (18).toFloat(), ctx.engine.masterPeakL());
    meter.removeFromLeft (4);
    theme::drawMeter (g, meter.removeFromLeft (18).toFloat(), ctx.engine.masterPeakR());
}

void TransportBar::resized()
{
    auto r = getLocalBounds().reduced (6, 7);
    r.removeFromLeft (100);
    r.removeFromRight (56);
    auto place = [&] (juce::Component& c, int w) { c.setBounds (r.removeFromLeft (w)); r.removeFromLeft (4); };
    place (browserBtn, 70);
    r.removeFromLeft (8);
    place (tempoLabel, 36);
    place (tempo, 110);
    place (metroBtn, 52);
    place (quantize, 120);
    r.removeFromLeft (12);
    place (playBtn, 56);
    place (stopBtn, 56);
    place (recBtn, 50);
    place (position, 96);
    place (loopBtn, 50);
    r.removeFromLeft (12);
    place (sessionBtn, 72);
    place (arrangeBtn, 72);
    r.removeFromLeft (12);
    place (undoBtn, 52);
    place (redoBtn, 52);
    place (exportBtn, 62);
    masterVol.setBounds (r.removeFromLeft (juce::jmin (140, r.getWidth())));
}

} // namespace tessera
