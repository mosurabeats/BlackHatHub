#pragma once
#include <juce_audio_formats/juce_audio_formats.h>
#include <map>
#include <memory>
#include <mutex>

namespace tessera
{

using SampleBuffer = std::shared_ptr<const juce::AudioBuffer<float>>;

// Loads audio files (WAV, AIFF, FLAC, Ogg, MP3 where the platform supports it), converts them to
// stereo at the engine sample rate and caches the result. Called on the message thread only.
class AudioFileCache
{
public:
    AudioFileCache();
    SampleBuffer get (const juce::String& path, double sampleRate);
    static double durationSeconds (const juce::File& f);
    juce::AudioFormatManager& formats() { return formatManager; }
    void clear();

private:
    juce::AudioFormatManager formatManager;
    std::map<juce::String, SampleBuffer> cache;
    std::mutex lock;
};

} // namespace tessera
