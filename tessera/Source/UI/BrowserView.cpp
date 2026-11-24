#include "Views.h"

namespace tessera
{

BrowserView::BrowserView (AppContext& c) : ctx (c)
{
    formats.registerBasicFormats();
    thread.startThread (juce::Thread::Priority::low);
    auto root = juce::File::getSpecialLocation (juce::File::userMusicDirectory);
    if (! root.isDirectory()) root = juce::File::getSpecialLocation (juce::File::userHomeDirectory);
    list.setDirectory (root, true, true);
    addAndMakeVisible (tree);
    tree.addListener (this);
    tree.setDragAndDropDescription ("TesseraFile");
    tree.setColour (juce::FileTreeComponent::backgroundColourId, theme::panel);
    tree.setColour (juce::FileTreeComponent::linesColourId, theme::line);
    tree.setColour (juce::FileTreeComponent::textColourId, theme::text);
    addAndMakeVisible (folderBtn);
    folderBtn.onClick = [this] { chooseFolder(); };
    addAndMakeVisible (rootLabel);
    rootLabel.setFont (theme::font (11.0f));
    rootLabel.setColour (juce::Label::textColourId, theme::textDim);
    rootLabel.setText (root.getFileName(), juce::dontSendNotification);
    ctx.browserSelectedFile = [this] { return selectedFile(); };
}

BrowserView::~BrowserView()
{
    ctx.browserSelectedFile = nullptr;
    tree.removeListener (this);
    thread.stopThread (2000);
}

void BrowserView::chooseFolder()
{
    chooser = std::make_unique<juce::FileChooser> ("Choose a sample folder", list.getDirectory());
    chooser->launchAsync (juce::FileBrowserComponent::openMode | juce::FileBrowserComponent::canSelectDirectories, [this] (const juce::FileChooser& fc)
    {
        auto f = fc.getResult();
        if (f.isDirectory())
        {
            list.setDirectory (f, true, true);
            rootLabel.setText (f.getFileName(), juce::dontSendNotification);
        }
    });
}

void BrowserView::fileClicked (const juce::File&, const juce::MouseEvent&) {}

void BrowserView::fileDoubleClicked (const juce::File& f)
{
    // Double-click: add to the first empty slot of the selected audio track (or a new audio track).
    if (! AppContext::isAudioFile (f.getFullPathName())) return;
    const auto& p = ctx.project();
    auto clip = AppContext::audioClipFromFile (f, p.tempo, paletteColour ((int) p.tracks.size()));
    if (clip == nullptr) return;
    const auto* sel = p.findTrack (ctx.selection.trackId);
    const juce::String targetId = sel && sel->kind == TrackKind::audio ? sel->id : juce::String();
    const int n = (int) p.tracks.size();
    ctx.ctl.edit ("Add audio clip", [clip, targetId, n] (Project& pr)
    {
        Track* t = targetId.isNotEmpty() ? pr.findTrack (targetId) : nullptr;
        if (t == nullptr)
        {
            pr.tracks.push_back (makeTrack (TrackKind::audio, clip->name, n));
            pr.ensureSlotCount();
            t = &pr.tracks.back();
        }
        clip->colour = t->colour;
        for (auto& s : t->slots) if (s == nullptr) { s = clip; return; }
        pr.scenes.push_back ({ juce::String (pr.scenes.size() + 1) });
        pr.ensureSlotCount();
        t->slots.back() = clip;
    });
}

void BrowserView::paint (juce::Graphics& g)
{
    g.fillAll (theme::panel);
    g.setColour (theme::textDim);
    g.setFont (theme::font (11.0f, true));
    g.drawText ("BROWSER", 8, 4, 100, 20, juce::Justification::centredLeft);
    g.setColour (theme::line);
    g.drawVerticalLine (getWidth() - 1, 0, (float) getHeight());
    g.setColour (theme::textDim);
    g.setFont (theme::font (10.5f));
    g.drawFittedText ("Drag files onto slots, lanes or drum pads. Double-click adds to the selected audio track.",
                      getLocalBounds().removeFromBottom (34).reduced (8, 2), juce::Justification::centredLeft, 2);
}

void BrowserView::resized()
{
    auto r = getLocalBounds();
    auto top = r.removeFromTop (28).reduced (6, 4);
    folderBtn.setBounds (top.removeFromRight (74));
    top.removeFromLeft (64);
    rootLabel.setBounds (top);
    r.removeFromBottom (36);
    tree.setBounds (r.reduced (2));
}

} // namespace tessera
