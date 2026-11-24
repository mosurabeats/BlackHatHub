#include "MainComponent.h"

namespace tessera
{

// Draggable bar between the main view and the bottom (devices + clip editor) area.
struct MainComponent::Divider : public juce::Component
{
    explicit Divider (MainComponent& m) : owner (m) { setMouseCursor (juce::MouseCursor::UpDownResizeCursor); }
    void paint (juce::Graphics& g) override { g.fillAll (theme::line); }
    void mouseDown (const juce::MouseEvent&) override { start = owner.bottomHeight; }
    void mouseDrag (const juce::MouseEvent& e) override
    {
        owner.bottomHeight = juce::jlimit (140, juce::jmax (140, owner.getHeight() - 200), start - e.getDistanceFromDragStartY());
        owner.resized();
    }
    MainComponent& owner;
    int start = 0;
};

MainComponent::MainComponent()
{
    juce::LookAndFeel::setDefaultLookAndFeel (&lnf);
    setLookAndFeel (&lnf);
    setWantsKeyboardFocus (true);

    ctl.setPublisher ([this] (std::shared_ptr<const Project> p) { engine.setProject (p); });
    ctl.addChangeListener (this);

    // Audio: 2 in / 2 out on the default device; restore previous settings if saved.
    auto settingsFile = juce::File::getSpecialLocation (juce::File::userApplicationDataDirectory).getChildFile ("Tessera").getChildFile ("audio-settings.xml");
    std::unique_ptr<juce::XmlElement> saved = juce::XmlDocument::parse (settingsFile);
    const auto err = deviceManager.initialise (2, 2, saved.get(), true);
    if (err.isNotEmpty()) DBG ("Audio device: " << err);
    deviceManager.addAudioCallback (&engine);
    for (auto& d : juce::MidiInput::getAvailableDevices())
        deviceManager.setMidiInputDeviceEnabled (d.identifier, true);
    deviceManager.addMidiInputDeviceCallback ({}, this);

#if ! JUCE_MAC
    menuBar = std::make_unique<juce::MenuBarComponent> (this);
    addAndMakeVisible (*menuBar);
#endif
    addAndMakeVisible (transport);
    addAndMakeVisible (browser);
    addAndMakeVisible (session);
    addChildComponent (arrangement);
    addAndMakeVisible (devices);
    addAndMakeVisible (clipEditor);
    divider = std::make_unique<Divider> (*this);
    addAndMakeVisible (*divider);

    transport.onViewChange = [this] (bool s) { showView (s); };
    transport.onExport = [this] { exportAudio(); };
    transport.onToggleBrowser = [this] { showBrowser = ! showBrowser; resized(); };

    if (! ctl.project().tracks.empty()) ctx.select (ctl.project().tracks[1].id);
    setSize (1400, 860);
    startTimerHz (30);
    updateTitle();
}

MainComponent::~MainComponent()
{
    auto dir = juce::File::getSpecialLocation (juce::File::userApplicationDataDirectory).getChildFile ("Tessera");
    dir.createDirectory();
    if (auto xml = deviceManager.createStateXml()) xml->writeTo (dir.getChildFile ("audio-settings.xml"));
    deviceManager.removeMidiInputDeviceCallback ({}, this);
    deviceManager.removeAudioCallback (&engine);
    deviceManager.closeAudioDevice();
    ctl.removeChangeListener (this);
    setLookAndFeel (nullptr);
    juce::LookAndFeel::setDefaultLookAndFeel (nullptr);
}

void MainComponent::paint (juce::Graphics& g) { g.fillAll (theme::bg); }

void MainComponent::resized()
{
    auto r = getLocalBounds();
    if (menuBar) menuBar->setBounds (r.removeFromTop (24));
    transport.setBounds (r.removeFromTop (46));
    browser.setVisible (showBrowser);
    if (showBrowser) browser.setBounds (r.removeFromLeft (230));
    auto bottom = r.removeFromBottom (juce::jmin (bottomHeight, juce::jmax (140, r.getHeight() - 160)));
    divider->setBounds (r.removeFromBottom (4));
    session.setBounds (r);
    arrangement.setBounds (r);
    devices.setBounds (bottom.removeFromTop (juce::jmin (206, bottom.getHeight() / 2)));
    clipEditor.setBounds (bottom);
}

void MainComponent::showView (bool s)
{
    sessionVisible = s;
    session.setVisible (s);
    arrangement.setVisible (! s);
    transport.setSessionView (s);
    menuItemsChanged();
}

void MainComponent::timerCallback()
{
    engine.pollRecording (ctl);   // also releases retired engine states
}

void MainComponent::changeListenerCallback (juce::ChangeBroadcaster*)
{
    updateTitle();
    ctx.updateLiveTrack();
    // keep the selection valid after undo / deletions
    if (ctl.project().findTrack (ctx.selection.trackId) == nullptr && ! ctl.project().tracks.empty())
        ctx.select (ctl.project().tracks.front().id);
    menuItemsChanged();
}

void MainComponent::updateTitle()
{
    auto name = ctl.file() == juce::File() ? juce::String ("Untitled") : ctl.file().getFileNameWithoutExtension();
    if (onTitleChange) onTitleChange ("Tessera - " + name + (ctl.isDirty() ? " *" : ""));
}

void MainComponent::togglePlay()
{
    if (engine.isPlaying())
    {
        if (engine.isRecording()) engine.stopRecording (ctl);
        engine.stop();
    }
    else engine.play();
}

// ------------------------------------------------------------------ MIDI input & computer keyboard

void MainComponent::handleIncomingMidiMessage (juce::MidiInput*, const juce::MidiMessage& m)
{
    const int track = ctx.liveTrackIndex.load();
    if (track < 0) return;
    if (m.isNoteOn()) engine.noteOn (track, m.getNoteNumber(), m.getFloatVelocity());
    else if (m.isNoteOff()) engine.noteOff (track, m.getNoteNumber());
}

static int keyToSemitone (int keyCode)
{
    static const juce::String keys = "awsedftgyhujkolp";   // C C# D D# E F F# G G# A A# B C C# D D#
    const int idx = keys.indexOfChar ((juce::juce_wchar) juce::CharacterFunctions::toLowerCase ((juce::juce_wchar) keyCode));
    return idx;
}

bool MainComponent::keyPressed (const juce::KeyPress& k)
{
    const auto mods = k.getModifiers();
    if (k == juce::KeyPress::spaceKey) { togglePlay(); return true; }
    if (k == juce::KeyPress::tabKey) { showView (! sessionVisible); return true; }
    if (mods.isCommandDown())
    {
        const auto c = juce::CharacterFunctions::toLowerCase (k.getTextCharacter() != 0 ? k.getTextCharacter() : (juce::juce_wchar) k.getKeyCode());
        if (c == 'z') { mods.isShiftDown() ? ctl.redo() : ctl.undo(); return true; }
        if (c == 'y') { ctl.redo(); return true; }
        if (c == 's') { saveProject (mods.isShiftDown()); return true; }
        if (c == 'o') { openProject(); return true; }
        if (c == 'n') { newProject(); return true; }
        if (c == 'e') { exportAudio(); return true; }
        if (c == 'r') { transport.toggleRecord(); return true; }
        return false;
    }
    if (mods.isAnyModifierKeyDown() && ! mods.isShiftDown()) return false;
    const int code = k.getKeyCode();
    const auto ch = juce::CharacterFunctions::toLowerCase ((juce::juce_wchar) code);
    if (ch == 'z') { octave = juce::jmax (0, octave - 1); return true; }
    if (ch == 'x') { octave = juce::jmin (8, octave + 1); return true; }
    const int semi = keyToSemitone (code);
    if (semi >= 0)
    {
        const int track = ctx.liveTrackIndex.load();
        if (track >= 0 && ! heldComputerKeys.count (code))
        {
            const int note = juce::jlimit (0, 127, (octave + 1) * 12 + semi);
            heldComputerKeys[code] = note;
            engine.noteOn (track, note, 0.8f);
        }
        return true;
    }
    return false;
}

bool MainComponent::keyStateChanged (bool)
{
    const int track = ctx.liveTrackIndex.load();
    for (auto it = heldComputerKeys.begin(); it != heldComputerKeys.end();)
    {
        if (! juce::KeyPress::isKeyCurrentlyDown (it->first))
        {
            if (track >= 0) engine.noteOff (track, it->second);
            it = heldComputerKeys.erase (it);
        }
        else ++it;
    }
    return false;
}

// ------------------------------------------------------------------ menus

juce::StringArray MainComponent::getMenuBarNames() { return { "File", "Edit", "Create", "View", "Transport", "Help" }; }

juce::PopupMenu MainComponent::getMenuForIndex (int index, const juce::String&)
{
    juce::PopupMenu m;
    auto item = [&] (int id, const juce::String& text, const juce::String& shortcut = {}, bool enabled = true)
    {
        juce::PopupMenu::Item it (text);
        it.setID (id).setEnabled (enabled);
        it.shortcutKeyDescription = shortcut.replace ("command", "Cmd").replace ("shift", "Shift").replace (" + ", "+");
        m.addItem (it);
    };
    switch (index)
    {
        case 0:
            item (mNew, "New Project", "command + N");
            item (mDemo, "Open Demo Project");
            item (mOpen, "Open...", "command + O");
            item (mSave, "Save", "command + S");
            item (mSaveAs, "Save As...", "shift + command + S");
            m.addSeparator();
            item (mExport, "Export Arrangement to WAV...", "command + E");
            m.addSeparator();
            item (mSettings, "Audio / MIDI Settings...");
#if ! JUCE_MAC
            m.addSeparator();
            item (mQuit, "Quit");
#endif
            break;
        case 1:
            item (mUndo, ctl.canUndo() ? "Undo " + ctl.undoName() : juce::String ("Undo"), "command + Z", ctl.canUndo());
            item (mRedo, "Redo", "shift + command + Z", ctl.canRedo());
            m.addSeparator();
            item (mDelete, "Delete Selected Clip", {}, ctx.selection.where != Selection::Where::none);
            break;
        case 2:
            item (mAddMidi, "MIDI Track");
            item (mAddAudio, "Audio Track");
            item (mAddScene, "Scene");
            break;
        case 3:
            m.addItem (juce::PopupMenu::Item ("Session View").setID (mSession).setTicked (sessionVisible));
            m.addItem (juce::PopupMenu::Item ("Arrangement View").setID (mArrange).setTicked (! sessionVisible));
            m.addItem (juce::PopupMenu::Item ("Browser").setID (mBrowser).setTicked (showBrowser));
            break;
        case 4:
            item (mPlay, engine.isPlaying() ? "Stop" : "Play", "spacebar");
            item (mRecord, engine.isRecording() ? "Stop Recording" : "Record", "command + R");
            break;
        case 5:
            item (mHelp, "Keyboard & Workflow Help");
            break;
        default: break;
    }
    return m;
}

void MainComponent::menuItemSelected (int id, int)
{
    switch (id)
    {
        case mNew: newProject(); break;
        case mDemo:
            confirmDiscard ([this] { engine.stop(); engine.stop(); ctl.loadDemo(); ctx.select (ctl.project().tracks.front().id); });
            break;
        case mOpen: openProject(); break;
        case mSave: saveProject (false); break;
        case mSaveAs: saveProject (true); break;
        case mExport: exportAudio(); break;
        case mSettings: showAudioSettings(); break;
        case mQuit: juce::JUCEApplication::getInstance()->systemRequestedQuit(); break;
        case mUndo: ctl.undo(); break;
        case mRedo: ctl.redo(); break;
        case mDelete:
            if (ctx.selection.where == Selection::Where::arrangement) arrangement.deleteSelected();
            else if (ctx.selection.where == Selection::Where::slot)
            {
                auto sel = ctx.selection;
                ctl.edit ("Delete clip", [sel] (Project& p) { if (auto* t = p.findTrack (sel.trackId)) t->slots[(size_t) sel.slot] = nullptr; });
                ctx.select (sel.trackId);
            }
            break;
        case mAddMidi:
        case mAddAudio:
        {
            const auto kind = id == mAddMidi ? TrackKind::midi : TrackKind::audio;
            const int n = (int) ctl.project().tracks.size();
            ctl.edit ("Add track", [kind, n] (Project& p)
            { p.tracks.push_back (makeTrack (kind, (kind == TrackKind::midi ? "MIDI " : "Audio ") + juce::String (n + 1), n)); });
            ctx.select (ctl.project().tracks.back().id);
            break;
        }
        case mAddScene: ctl.edit ("Add scene", [] (Project& p) { p.scenes.push_back ({ juce::String (p.scenes.size() + 1) }); }); break;
        case mSession: showView (true); break;
        case mArrange: showView (false); break;
        case mBrowser: showBrowser = ! showBrowser; resized(); menuItemsChanged(); break;
        case mPlay: togglePlay(); break;
        case mRecord: transport.toggleRecord(); break;
        case mHelp:
            juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::InfoIcon, "Tessera shortcuts",
                "Space: play / stop (stop twice to return to start)\n"
                "Tab: switch Session / Arrangement\n"
                "A W S E D F T G Y H U J K: play notes on the armed (or selected) MIDI track;  Z / X: octave\n"
                "Cmd+Z / Shift+Cmd+Z: undo / redo;  Cmd+S save;  Cmd+O open;  Cmd+E export;  Cmd+R record\n\n"
                "Session: click a clip's triangle to launch it, a scene's triangle to launch the row.\n"
                "Double-click an empty MIDI slot to create a clip. Arm a MIDI track (R) and click an empty slot to record 4 bars into it.\n"
                "Arrangement: double-click a lane to create a clip, drag to move, drag the right edge to resize, shift-drag the ruler to set the loop.\n"
                "Drop audio files from the browser or Finder onto slots, lanes or drum pads.");
            break;
        default: break;
    }
}

// ------------------------------------------------------------------ files

void MainComponent::confirmDiscard (std::function<void()> proceed)
{
    if (! ctl.isDirty()) { proceed(); return; }
    juce::AlertWindow::showYesNoCancelBox (juce::MessageBoxIconType::QuestionIcon, "Unsaved changes",
        "Save changes to the current project first?", "Save", "Don't Save", "Cancel", this,
        juce::ModalCallbackFunction::create ([this, proceed] (int r)
        {
            if (r == 1) saveProject (false, [proceed] (bool ok) { if (ok) proceed(); });
            else if (r == 2) proceed();
        }));
}

void MainComponent::newProject()
{
    confirmDiscard ([this]
    {
        engine.stop();
        engine.stop();
        ctl.newProject();
        ctx.select (ctl.project().tracks.empty() ? juce::String() : ctl.project().tracks.front().id);
    });
}

void MainComponent::openProject()
{
    confirmDiscard ([this]
    {
        chooser = std::make_unique<juce::FileChooser> ("Open project", juce::File::getSpecialLocation (juce::File::userMusicDirectory), "*.tessera");
        chooser->launchAsync (juce::FileBrowserComponent::openMode | juce::FileBrowserComponent::canSelectFiles, [this] (const juce::FileChooser& fc)
        {
            auto f = fc.getResult();
            if (f == juce::File()) return;
            juce::String err;
            engine.stop();
            engine.stop();
            if (! ctl.load (f, err))
                juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::WarningIcon, "Could not open project", err);
            else if (! ctl.project().tracks.empty())
                ctx.select (ctl.project().tracks.front().id);
        });
    });
}

void MainComponent::saveProject (bool saveAs, std::function<void (bool)> then)
{
    auto doSave = [this, then] (juce::File f)
    {
        if (f == juce::File()) { if (then) then (false); return; }
        f = f.withFileExtension ("tessera");
        juce::String err;
        const bool ok = ctl.save (f, err);
        if (! ok) juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::WarningIcon, "Save failed", err);
        updateTitle();
        if (then) then (ok);
    };
    if (! saveAs && ctl.file() != juce::File()) { doSave (ctl.file()); return; }
    chooser = std::make_unique<juce::FileChooser> ("Save project", juce::File::getSpecialLocation (juce::File::userMusicDirectory).getChildFile ("Untitled.tessera"), "*.tessera");
    chooser->launchAsync (juce::FileBrowserComponent::saveMode | juce::FileBrowserComponent::warnAboutOverwriting,
                          [doSave] (const juce::FileChooser& fc) { doSave (fc.getResult()); });
}

void MainComponent::exportAudio()
{
    if (ctl.project().arrangementEndBeat() <= 0)
    {
        juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::InfoIcon, "Nothing to export",
            "Export renders the Arrangement. Place clips on the timeline first (right-click a session clip > Copy to arrangement).");
        return;
    }
    auto start = ctl.file() != juce::File() ? ctl.file().withFileExtension ("wav")
                                            : juce::File::getSpecialLocation (juce::File::userMusicDirectory).getChildFile ("Tessera Export.wav");
    chooser = std::make_unique<juce::FileChooser> ("Export arrangement", start, "*.wav");
    chooser->launchAsync (juce::FileBrowserComponent::saveMode | juce::FileBrowserComponent::warnAboutOverwriting, [this] (const juce::FileChooser& fc)
    {
        auto f = fc.getResult();
        if (f == juce::File()) return;
        f = f.withFileExtension ("wav");
        auto snap = ctl.snapshot();
        struct Job : public juce::ThreadWithProgressWindow
        {
            Job (std::shared_ptr<const Project> p, juce::File o) : ThreadWithProgressWindow ("Exporting...", true, true), project (p), out (o) {}
            void run() override
            {
                std::atomic<bool> cancel { false };
                ExportOptions opts;
                std::atomic<double> prog { 0 };
                auto worker = std::thread ([&] { ok = exportArrangement (project, out, opts, error, &prog, &cancel); done = true; });
                while (! done.load())
                {
                    setProgress (prog.load());
                    if (threadShouldExit()) cancel = true;
                    wait (50);
                }
                worker.join();
            }
            std::shared_ptr<const Project> project;
            juce::File out;
            juce::String error;
            bool ok = false;
            std::atomic<bool> done { false };
        };
        Job job (snap, f);
        job.runThread();
        if (job.ok)
            juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::InfoIcon, "Export complete", f.getFullPathName());
        else
            juce::AlertWindow::showMessageBoxAsync (juce::MessageBoxIconType::WarningIcon, "Export failed", job.error);
    });
}

void MainComponent::showAudioSettings()
{
    auto* selector = new juce::AudioDeviceSelectorComponent (deviceManager, 0, 2, 2, 2, true, false, true, false);
    selector->setSize (520, 460);
    juce::DialogWindow::LaunchOptions o;
    o.content.setOwned (selector);
    o.dialogTitle = "Audio / MIDI Settings";
    o.dialogBackgroundColour = theme::panel;
    o.useNativeTitleBar = true;
    o.resizable = false;
    o.launchAsync();
}

} // namespace tessera
