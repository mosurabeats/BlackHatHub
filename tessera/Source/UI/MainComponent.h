#pragma once
#include "Views.h"
#include "../Engine/Exporter.h"
#include <thread>

namespace tessera
{

class MainComponent : public juce::Component, public juce::DragAndDropContainer, public juce::MenuBarModel,
                      private juce::MidiInputCallback, private juce::Timer, private juce::ChangeListener
{
public:
    MainComponent();
    ~MainComponent() override;

    void paint (juce::Graphics&) override;
    void resized() override;
    bool keyPressed (const juce::KeyPress&) override;
    bool keyStateChanged (bool isKeyDown) override;

    // MenuBarModel
    juce::StringArray getMenuBarNames() override;
    juce::PopupMenu getMenuForIndex (int index, const juce::String&) override;
    void menuItemSelected (int id, int) override;

    // File operations
    void newProject();
    void openProject();
    void saveProject (bool saveAs, std::function<void (bool)> then = {});
    void exportAudio();
    void showAudioSettings();
    void confirmDiscard (std::function<void()> proceed);
    bool hasUnsavedChanges() const { return ctl.isDirty(); }
    void loadDemo() { ctl.loadDemo(); ctx.select (ctl.project().tracks.front().id); }
    void showArrangement() { showView (false); }
    AppContext& context() { return ctx; }
    std::function<void (const juce::String&)> onTitleChange;

private:
    enum MenuIds { mNew = 1, mDemo, mOpen, mSave, mSaveAs, mExport, mSettings, mQuit, mUndo, mRedo, mDelete,
                   mAddMidi, mAddAudio, mAddScene, mSession, mArrange, mBrowser, mPlay, mRecord, mHelp };
    struct Divider;
    void handleIncomingMidiMessage (juce::MidiInput*, const juce::MidiMessage&) override;
    void timerCallback() override;
    void changeListenerCallback (juce::ChangeBroadcaster*) override;
    void showView (bool session);
    void updateTitle();
    void togglePlay();

    ProjectController ctl;
    AudioEngine engine;
    juce::AudioDeviceManager deviceManager;
    AppContext ctx { ctl, engine };
    theme::LookAndFeel lnf;
    juce::TooltipWindow tooltips { this, 600 };

    std::unique_ptr<juce::MenuBarComponent> menuBar;
    TransportBar transport { ctx };
    BrowserView browser { ctx };
    SessionView session { ctx };
    ArrangementView arrangement { ctx };
    DeviceView devices { ctx };
    ClipEditor clipEditor { ctx };
    std::unique_ptr<Divider> divider;
    bool showBrowser = true, sessionVisible = true;
    int bottomHeight = 400;

    std::unique_ptr<juce::FileChooser> chooser;
    std::map<int, int> heldComputerKeys;   // key code -> note
    int octave = 4;                         // computer keyboard: 'A' = C4 (MIDI 60)
};

} // namespace tessera
