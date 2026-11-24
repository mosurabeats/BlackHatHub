#include "AudioFileCache.h"

namespace tessera
{

AudioFileCache::AudioFileCache() { formatManager.registerBasicFormats(); }

void AudioFileCache::clear()
{
    std::scoped_lock l (lock);
    cache.clear();
}

double AudioFileCache::durationSeconds (const juce::File& f)
{
    juce::AudioFormatManager fm;
    fm.registerBasicFormats();
    std::unique_ptr<juce::AudioFormatReader> r (fm.createReaderFor (f));
    return r ? (double) r->lengthInSamples / r->sampleRate : 0.0;
}

SampleBuffer AudioFileCache::get (const juce::String& path, double sampleRate)
{
    if (path.isEmpty()) return nullptr;
    auto key = path + "@" + juce::String (sampleRate);
    std::scoped_lock l (lock);
    if (auto it = cache.find (key); it != cache.end()) return it->second;

    std::unique_ptr<juce::AudioFormatReader> reader (formatManager.createReaderFor (juce::File (path)));
    if (reader == nullptr || reader->lengthInSamples <= 0 || reader->lengthInSamples > (juce::int64) 48000 * 60 * 20)
    {
        cache[key] = nullptr;   // missing / unreadable / longer than 20 minutes
        return nullptr;
    }
    const int srcLen = (int) reader->lengthInSamples;
    juce::AudioBuffer<float> src (2, srcLen);
    reader->read (&src, 0, srcLen, 0, true, reader->numChannels > 1);
    if (reader->numChannels == 1) src.copyFrom (1, 0, src, 0, 0, srcLen);

    auto out = std::make_shared<juce::AudioBuffer<float>>();
    if (std::abs (reader->sampleRate - sampleRate) < 0.5)
    {
        *out = std::move (src);
    }
    else
    {
        const double ratio = reader->sampleRate / sampleRate;
        const int dstLen = (int) std::ceil (srcLen / ratio);
        out->setSize (2, dstLen);
        for (int ch = 0; ch < 2; ++ch)
        {
            juce::LagrangeInterpolator interp;
            interp.process (ratio, src.getReadPointer (ch), out->getWritePointer (ch), dstLen, srcLen, 0);
        }
    }
    cache[key] = out;
    return out;
}

} // namespace tessera
