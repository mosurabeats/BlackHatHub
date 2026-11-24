#pragma once
#include <juce_core/juce_core.h>

namespace tessera
{

// Hands a small POD parameter struct from the message thread to the audio thread without
// blocking the audio thread: the writer locks; the reader only try-locks and otherwise keeps
// using its previous copy.
template <typename T>
class ParamExchange
{
public:
    void write (const T& v)
    {
        const juce::SpinLock::ScopedLockType l (lock);
        pending = v;
        dirty = true;
    }

    // Audio thread. Returns true if `active` changed.
    bool read (T& active)
    {
        const juce::SpinLock::ScopedTryLockType l (lock);
        if (! l.isLocked() || ! dirty) return false;
        active = pending;
        dirty = false;
        return true;
    }

private:
    juce::SpinLock lock;
    T pending {};
    bool dirty = false;
};

} // namespace tessera
