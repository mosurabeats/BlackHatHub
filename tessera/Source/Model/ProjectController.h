#pragma once
// Owns the editable Project on the message thread: edits, undo/redo, save/load, and publishing
// immutable snapshots to the audio engine.
#include "Project.h"
#include <functional>

namespace tessera
{

class ProjectController : public juce::ChangeBroadcaster
{
public:
    using Publisher = std::function<void (std::shared_ptr<const Project>)>;

    ProjectController();

    const Project& project() const { return current; }
    std::shared_ptr<const Project> snapshot() const { return published; }

    // Apply an edit. A named edit is undoable; pass undoable=false for continuous gestures
    // (e.g. dragging a fader) and call beginGesture() first to record a single undo step.
    void edit (const juce::String& name, const std::function<void (Project&)>& fn, bool undoable = true);
    void beginGesture (const juce::String& name);

    bool canUndo() const { return ! undoStack.empty(); }
    bool canRedo() const { return ! redoStack.empty(); }
    bool undo();
    bool redo();
    juce::String undoName() const { return undoStack.empty() ? juce::String() : undoStack.back().first; }

    void setPublisher (Publisher p);
    void newProject();
    void loadDemo();
    bool load (const juce::File& f, juce::String& error);
    bool save (const juce::File& f, juce::String& error);
    juce::File file() const { return currentFile; }
    bool isDirty() const { return dirty; }

    void replaceProject (Project p);  // used by recording commit etc. (undoable)

private:
    void publish();

    Project current;
    std::shared_ptr<const Project> published;
    std::vector<std::pair<juce::String, Project>> undoStack, redoStack;
    Publisher publisher;
    juce::File currentFile;
    bool dirty = false;
    static constexpr size_t maxUndo = 200;
};

} // namespace tessera
