#pragma once
// Declarations of Tessera's main views.
#include "AppContext.h"
#include "Theme.h"

namespace tessera
{

// ------------------------------------------------------------------ transport bar
class TransportBar : public juce::Component, private juce::ChangeListener, private juce::Timer
{
public:
    TransportBar (AppContext& ctx);
    ~TransportBar() override;
    void resized() override;
    void paint (juce::Graphics&) override;
    std::function<void (bool session)> onViewChange;
    std::function<void()> onExport, onToggleBrowser;
    void setSessionView (bool s);
    void toggleRecord();

private:
    void changeListenerCallback (juce::ChangeBroadcaster*) override { refresh(); }
    void timerCallback() override;
    void refresh();
    AppContext& ctx;
    juce::TextButton playBtn { "Play" }, stopBtn { "Stop" }, recBtn { "Rec" }, metroBtn { "Click" }, loopBtn { "Loop" },
        sessionBtn { "Session" }, arrangeBtn { "Arrange" }, undoBtn { "Undo" }, redoBtn { "Redo" }, exportBtn { "Export" },
        browserBtn { "Browser" };
    juce::Slider tempo { juce::Slider::IncDecButtons, juce::Slider::TextBoxLeft };
    juce::ComboBox quantize;
    juce::Slider masterVol { juce::Slider::LinearHorizontal, juce::Slider::NoTextBox };
    juce::Label position, tempoLabel { {}, "BPM" };
    bool sessionView = true;
};

// ------------------------------------------------------------------ session (clip launcher) view
class SessionView : public juce::Component, private juce::ChangeListener, private juce::Timer,
                    public juce::FileDragAndDropTarget, public juce::DragAndDropTarget
{
public:
    SessionView (AppContext& ctx);
    ~SessionView() override;
    void paint (juce::Graphics&) override;
    void resized() override;
    void mouseDown (const juce::MouseEvent&) override;
    void mouseDoubleClick (const juce::MouseEvent&) override;
    bool isInterestedInFileDrag (const juce::StringArray&) override;
    void filesDropped (const juce::StringArray&, int x, int y) override;
    bool isInterestedInDragSource (const SourceDetails&) override;
    void itemDropped (const SourceDetails&) override;

    static constexpr int colW = 132, headerH = 30, rowH = 28, sceneColW = 96, stopRowH = 24, mixerH = 176;

private:
    struct Strip;
    void changeListenerCallback (juce::ChangeBroadcaster*) override;
    void timerCallback() override { repaint(); }
    void rebuildStrips();
    void dropAudioAt (const juce::File& f, juce::Point<int> pos);
    bool cellAt (juce::Point<int> p, int& track, int& scene) const;
    juce::Rectangle<int> cellRect (int track, int scene) const;
    void trackMenu (int track);
    void clipMenu (int track, int scene);
    void sceneMenu (int scene);
    AppContext& ctx;
    juce::OwnedArray<Strip> strips;
    juce::TextButton stopAllBtn { "Stop All" };
    int scrollX = 0;
};

// ------------------------------------------------------------------ arrangement (timeline) view
class ArrangementView : public juce::Component, private juce::ChangeListener, private juce::Timer,
                        public juce::FileDragAndDropTarget, public juce::DragAndDropTarget
{
public:
    ArrangementView (AppContext& ctx);
    ~ArrangementView() override;
    void paint (juce::Graphics&) override;
    void resized() override;
    void mouseDown (const juce::MouseEvent&) override;
    void mouseDrag (const juce::MouseEvent&) override;
    void mouseUp (const juce::MouseEvent&) override;
    void mouseDoubleClick (const juce::MouseEvent&) override;
    void mouseWheelMove (const juce::MouseEvent&, const juce::MouseWheelDetails&) override;
    void mouseMove (const juce::MouseEvent&) override;
    bool keyPressed (const juce::KeyPress&) override;
    bool isInterestedInFileDrag (const juce::StringArray&) override;
    void filesDropped (const juce::StringArray&, int x, int y) override;
    bool isInterestedInDragSource (const SourceDetails&) override;
    void itemDropped (const SourceDetails&) override;
    void deleteSelected();

    static constexpr int headerW = 150, rulerH = 26, laneH = 64;

private:
    void changeListenerCallback (juce::ChangeBroadcaster*) override { repaint(); }
    void timerCallback() override;
    double xToBeat (int x) const { return scrollBeats + (x - headerW) / pxPerBeat; }
    int beatToX (double b) const { return headerW + (int) std::round ((b - scrollBeats) * pxPerBeat); }
    int laneAt (int y) const { return y < rulerH ? -1 : (y - rulerH + scrollY) / laneH; }
    double snap (double beat) const;
    bool hitPlacement (juce::Point<int> p, int& track, int& index, bool& onRightEdge) const;
    void dropAudio (const juce::File& f, juce::Point<int> pos);
    AppContext& ctx;
    double pxPerBeat = 24, scrollBeats = 0;
    int scrollY = 0;
    enum class Drag { none, move, resize, loop, scrub } drag = Drag::none;
    int dragTrack = -1, dragIndex = -1;
    double dragStartBeat = 0, dragOrigStart = 0, dragOrigLen = 0;
    int dragOrigTrack = -1;
    bool dragBegun = false;
};

// ------------------------------------------------------------------ clip editor (piano roll / audio)
class ClipEditor : public juce::Component, private juce::ChangeListener, private juce::Timer
{
public:
    ClipEditor (AppContext& ctx);
    ~ClipEditor() override;
    void paint (juce::Graphics&) override;
    void resized() override;
    void mouseDown (const juce::MouseEvent&) override;
    void mouseDrag (const juce::MouseEvent&) override;
    void mouseUp (const juce::MouseEvent&) override;
    void mouseDoubleClick (const juce::MouseEvent&) override;
    void mouseWheelMove (const juce::MouseEvent&, const juce::MouseWheelDetails&) override;
    bool keyPressed (const juce::KeyPress&) override;

private:
    void changeListenerCallback (juce::ChangeBroadcaster*) override;
    void timerCallback() override { if (isShowing()) repaint (gridArea()); }
    void refreshControls();
    juce::Rectangle<int> gridArea() const;
    int pitchToY (int pitch) const;
    int yToPitch (int y) const;
    double xToBeat (int x) const;
    int beatToX (double b) const;
    int noteAt (juce::Point<int> p, bool& rightEdge) const;
    double gridBeats() const;
    void loadThumbnail();

    AppContext& ctx;
    juce::Label title;
    juce::ComboBox gridBox;
    juce::Slider lengthSlider { juce::Slider::IncDecButtons, juce::Slider::TextBoxLeft };
    juce::ToggleButton loopToggle { "Loop" }, warpToggle { "Warp" };
    juce::TextButton quantizeBtn { "Quantize" }, dupBtn { "x2" };
    juce::Slider sourceTempo { juce::Slider::IncDecButtons, juce::Slider::TextBoxLeft };
    juce::Slider gainSlider { juce::Slider::LinearHorizontal, juce::Slider::TextBoxRight };
    juce::AudioFormatManager formats;
    juce::AudioThumbnailCache thumbCache { 8 };
    juce::AudioThumbnail thumb { 256, formats, thumbCache };
    juce::String thumbFile;
    int topPitch = 84;
    float noteH = 10;
    // gesture state
    int dragNote = -1;
    bool dragResize = false;
    double dragBeatOffset = 0;
    std::vector<Note> dragOriginal;
    int selectedNote = -1;
    int previewPitch = -1;
};

// ------------------------------------------------------------------ device chain (instrument + effects)
class DeviceView : public juce::Component, private juce::ChangeListener, public juce::FileDragAndDropTarget
{
public:
    DeviceView (AppContext& ctx);
    ~DeviceView() override;
    void paint (juce::Graphics&) override;
    void resized() override;
    bool isInterestedInFileDrag (const juce::StringArray&) override;
    void filesDropped (const juce::StringArray&, int x, int y) override;
    void mouseDown (const juce::MouseEvent&) override;
    void mouseUp (const juce::MouseEvent&) override;

private:
    struct Panel;
    void changeListenerCallback (juce::ChangeBroadcaster*) override;
    void rebuild();
    juce::Rectangle<int> padRect (int pad) const;
    AppContext& ctx;
    struct Content : public juce::Component
    {
        std::function<void (juce::Graphics&)> overlay;
        void paintOverChildren (juce::Graphics& g) override { if (overlay) overlay (g); }
    };
    juce::Viewport viewport;
    Content content;
    juce::OwnedArray<Panel> panels;
    juce::TextButton addFx { "+ Effect" }, instType { "Instrument" };
    juce::String builtFor;            // structure key: rebuild only when the chain layout changes
    juce::Rectangle<int> padArea;
    int heldPad = -1;
};

// ------------------------------------------------------------------ file browser
class BrowserView : public juce::Component, private juce::FileBrowserListener
{
public:
    BrowserView (AppContext& ctx);
    ~BrowserView() override;
    void resized() override;
    void paint (juce::Graphics&) override;
    juce::File selectedFile() const { return tree.getSelectedFile(); }

private:
    void selectionChanged() override {}
    void fileClicked (const juce::File&, const juce::MouseEvent&) override;
    void fileDoubleClicked (const juce::File&) override;
    void browserRootChanged (const juce::File&) override {}
    void chooseFolder();
    AppContext& ctx;
    juce::WildcardFileFilter filter { "*.wav;*.aif;*.aiff;*.flac;*.ogg;*.mp3;*.m4a;*.caf", "*", "Audio" };
    juce::TimeSliceThread thread { "Tessera browser" };
    juce::DirectoryContentsList list { &filter, thread };
    juce::FileTreeComponent tree { list };
    juce::TextButton folderBtn { "Folder..." };
    juce::Label rootLabel;
    std::unique_ptr<juce::FileChooser> chooser;
    juce::AudioFormatManager formats;
    std::unique_ptr<juce::AudioTransportSource> previewTransport;
};

} // namespace tessera
