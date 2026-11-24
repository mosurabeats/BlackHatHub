#include "ProjectController.h"

namespace tessera
{

ProjectController::ProjectController() : current (Project::createDefault())
{
    published = std::make_shared<const Project> (current);
}

void ProjectController::setPublisher (Publisher p)
{
    publisher = std::move (p);
    publish();
}

void ProjectController::publish()
{
    published = std::make_shared<const Project> (current);
    if (publisher) publisher (published);
    sendChangeMessage();
}

void ProjectController::beginGesture (const juce::String& name)
{
    undoStack.emplace_back (name, current);
    if (undoStack.size() > maxUndo) undoStack.erase (undoStack.begin());
    redoStack.clear();
}

void ProjectController::edit (const juce::String& name, const std::function<void (Project&)>& fn, bool undoable)
{
    if (undoable) beginGesture (name);
    fn (current);
    current.ensureSlotCount();
    dirty = true;
    publish();
}

bool ProjectController::undo()
{
    if (undoStack.empty()) return false;
    redoStack.emplace_back (undoStack.back().first, current);
    current = std::move (undoStack.back().second);
    undoStack.pop_back();
    dirty = true;
    publish();
    return true;
}

bool ProjectController::redo()
{
    if (redoStack.empty()) return false;
    undoStack.emplace_back (redoStack.back().first, current);
    current = std::move (redoStack.back().second);
    redoStack.pop_back();
    dirty = true;
    publish();
    return true;
}

void ProjectController::newProject()
{
    current = Project::createDefault();
    undoStack.clear();
    redoStack.clear();
    currentFile = juce::File();
    dirty = false;
    publish();
}

void ProjectController::loadDemo()
{
    newProject();
    current = Project::createDemo();
    dirty = false;
    publish();
}

bool ProjectController::load (const juce::File& f, juce::String& error)
{
    Project p;
    if (! Project::loadFrom (f, p, error)) return false;
    current = std::move (p);
    undoStack.clear();
    redoStack.clear();
    currentFile = f;
    dirty = false;
    publish();
    return true;
}

bool ProjectController::save (const juce::File& f, juce::String& error)
{
    if (! current.saveTo (f, error)) return false;
    currentFile = f;
    dirty = false;
    sendChangeMessage();
    return true;
}

void ProjectController::replaceProject (Project p)
{
    beginGesture ("Record");
    current = std::move (p);
    current.ensureSlotCount();
    dirty = true;
    publish();
}

} // namespace tessera
