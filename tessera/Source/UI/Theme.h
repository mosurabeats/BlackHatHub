#pragma once
#include <juce_gui_extra/juce_gui_extra.h>
#include <juce_audio_utils/juce_audio_utils.h>

namespace tessera::theme
{
// Tessera palette: deep blue-slate surfaces, teal accent, amber for record/queued.
inline const juce::Colour bg       { 0xff101318 };
inline const juce::Colour panel    { 0xff171b22 };
inline const juce::Colour panelHi  { 0xff1f242d };
inline const juce::Colour cell     { 0xff232933 };
inline const juce::Colour line     { 0xff2c3440 };
inline const juce::Colour text     { 0xffdde3ea };
inline const juce::Colour textDim  { 0xff8591a0 };
inline const juce::Colour accent   { 0xff4fd1b8 };
inline const juce::Colour play     { 0xff5fd47a };
inline const juce::Colour record   { 0xffef5b5b };
inline const juce::Colour queued   { 0xffe8b04a };

juce::Font font (float size, bool bold = false);

class LookAndFeel : public juce::LookAndFeel_V4
{
public:
    LookAndFeel();
    void drawRotarySlider (juce::Graphics&, int x, int y, int w, int h, float pos, float start, float end, juce::Slider&) override;
    void drawLinearSlider (juce::Graphics&, int x, int y, int w, int h, float pos, float min, float max,
                           juce::Slider::SliderStyle, juce::Slider&) override;
    void drawButtonBackground (juce::Graphics&, juce::Button&, const juce::Colour&, bool over, bool down) override;
    juce::Font getTextButtonFont (juce::TextButton&, int h) override { return font (juce::jmin (13.0f, h * 0.55f)); }
    juce::Font getLabelFont (juce::Label&) override { return font (12.5f); }
};

void drawMeter (juce::Graphics& g, juce::Rectangle<float> r, float level);
} // namespace tessera::theme
