#include "Exporter.h"

namespace tessera
{

bool exportArrangement (std::shared_ptr<const Project> project, const juce::File& out, const ExportOptions& opts,
                        juce::String& error, std::atomic<double>* progress, std::atomic<bool>* cancel)
{
    if (project == nullptr) { error = "No project"; return false; }
    const double endBeat = opts.endBeat >= 0 ? opts.endBeat : project->arrangementEndBeat();
    if (endBeat <= opts.startBeat) { error = "The arrangement is empty: place clips on the timeline before exporting."; return false; }

    // Render without the loop region and metronome.
    auto p = std::make_shared<Project> (*project);
    p->loopEnabled = false;
    p->metronome = false;

    AudioEngine engine;
    const int block = 512;
    engine.prepare (opts.sampleRate, block);
    engine.setProject (p);
    engine.locate (opts.startBeat);
    engine.play();

    out.deleteFile();
    std::unique_ptr<juce::OutputStream> os (out.createOutputStream());
    if (os == nullptr) { error = "Cannot write " + out.getFullPathName(); return false; }
    juce::WavAudioFormat wav;
    std::unique_ptr<juce::AudioFormatWriter> writer (wav.createWriterFor (os.get(), opts.sampleRate, 2, opts.bitDepth, {}, 0));
    if (writer == nullptr) { error = "Unsupported WAV format"; return false; }
    os.release();

    const double seconds = (endBeat - opts.startBeat) * 60.0 / p->tempo + opts.tailSeconds;
    const juce::int64 total = (juce::int64) std::ceil (seconds * opts.sampleRate);
    juce::AudioBuffer<float> buf (2, block);
    for (juce::int64 done = 0; done < total; done += block)
    {
        if (cancel && cancel->load()) { writer.reset(); out.deleteFile(); error = "Export cancelled"; return false; }
        const int n = (int) juce::jmin ((juce::int64) block, total - done);
        engine.renderBlock (buf.getArrayOfWritePointers(), 2, nullptr, 0, n);
        if (! writer->writeFromAudioSampleBuffer (buf, 0, n)) { error = "Write failed (disk full?)"; return false; }
        if (progress) progress->store ((double) done / (double) total);
    }
    writer.reset();
    if (progress) progress->store (1.0);
    return true;
}

} // namespace tessera
