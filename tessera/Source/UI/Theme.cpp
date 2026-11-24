#include "Theme.h"

namespace tessera::theme
{

juce::Font font (float size, bool bold)
{
    return juce::Font (juce::FontOptions (size, bold ? juce::Font::bold : juce::Font::plain));
}

LookAndFeel::LookAndFeel()
{
    setColourScheme ({ bg, panel, panelHi, line, text, accent, juce::Colours::black, panelHi, text });
    setColour (juce::ResizableWindow::backgroundColourId, bg);
    setColour (juce::TextButton::buttonColourId, cell);
    setColour (juce::TextButton::buttonOnColourId, accent.withAlpha (0.85f));
    setColour (juce::TextButton::textColourOffId, text);
    setColour (juce::TextButton::textColourOnId, bg);
    setColour (juce::Slider::thumbColourId, accent);
    setColour (juce::Slider::trackColourId, accent.withAlpha (0.7f));
    setColour (juce::Slider::rotarySliderFillColourId, accent);
    setColour (juce::Slider::rotarySliderOutlineColourId, line);
    setColour (juce::Slider::textBoxTextColourId, text);
    setColour (juce::Slider::textBoxOutlineColourId, juce::Colours::transparentBlack);
    setColour (juce::Label::textColourId, text);
    setColour (juce::ComboBox::backgroundColourId, cell);
    setColour (juce::ComboBox::outlineColourId, line);
    setColour (juce::PopupMenu::backgroundColourId, panelHi);
    setColour (juce::PopupMenu::highlightedBackgroundColourId, accent.withAlpha (0.3f));
    setColour (juce::TreeView::backgroundColourId, panel);
    setColour (juce::DirectoryContentsDisplayComponent::highlightColourId, accent.withAlpha (0.3f));
    setColour (juce::ScrollBar::thumbColourId, line.brighter (0.3f));
}

void LookAndFeel::drawRotarySlider (juce::Graphics& g, int x, int y, int w, int h, float pos, float start, float end, juce::Slider& s)
{
    auto r = juce::Rectangle<float> ((float) x, (float) y, (float) w, (float) h).reduced (4);
    const float radius = juce::jmin (r.getWidth(), r.getHeight()) * 0.5f;
    const auto c = r.getCentre();
    const float angle = start + pos * (end - start);
    juce::Path bgArc, valArc;
    bgArc.addCentredArc (c.x, c.y, radius, radius, 0, start, end, true);
    g.setColour (line);
    g.strokePath (bgArc, juce::PathStrokeType (3.0f, juce::PathStrokeType::curved, juce::PathStrokeType::rounded));
    const bool bipolar = s.getMinimum() < 0 && s.getMaximum() > 0;
    const float from = bipolar ? (start + end) * 0.5f : start;
    valArc.addCentredArc (c.x, c.y, radius, radius, 0, juce::jmin (from, angle), juce::jmax (from, angle), true);
    g.setColour (s.isEnabled() ? accent : textDim);
    g.strokePath (valArc, juce::PathStrokeType (3.0f, juce::PathStrokeType::curved, juce::PathStrokeType::rounded));
    g.setColour (text);
    g.drawLine (c.x, c.y, c.x + (radius - 3) * std::sin (angle), c.y - (radius - 3) * std::cos (angle), 2.0f);
}

void LookAndFeel::drawLinearSlider (juce::Graphics& g, int x, int y, int w, int h, float pos, float, float,
                                    juce::Slider::SliderStyle style, juce::Slider& s)
{
    if (style != juce::Slider::LinearVertical && style != juce::Slider::LinearHorizontal)
    {
        LookAndFeel_V4::drawLinearSlider (g, x, y, w, h, pos, 0, 0, style, s);
        return;
    }
    const bool vertical = style == juce::Slider::LinearVertical;
    auto r = juce::Rectangle<float> ((float) x, (float) y, (float) w, (float) h);
    auto track = vertical ? r.withSizeKeepingCentre (4, r.getHeight()) : r.withSizeKeepingCentre (r.getWidth(), 4);
    g.setColour (line);
    g.fillRoundedRectangle (track, 2);
    g.setColour (accent.withAlpha (0.8f));
    if (vertical) g.fillRoundedRectangle (track.withTop (pos), 2);
    else g.fillRoundedRectangle (track.withRight (pos), 2);
    g.setColour (text);
    if (vertical) g.fillRoundedRectangle (juce::Rectangle<float> (r.getCentreX() - 9, pos - 3, 18, 6), 2);
    else g.fillRoundedRectangle (juce::Rectangle<float> (pos - 3, r.getCentreY() - 8, 6, 16), 2);
}

void LookAndFeel::drawButtonBackground (juce::Graphics& g, juce::Button& b, const juce::Colour& base, bool over, bool down)
{
    auto r = b.getLocalBounds().toFloat().reduced (0.5f);
    auto c = b.getToggleState() ? b.findColour (juce::TextButton::buttonOnColourId) : base;
    if (down) c = c.brighter (0.2f);
    else if (over) c = c.brighter (0.08f);
    g.setColour (c);
    g.fillRoundedRectangle (r, 3.0f);
    g.setColour (line.brighter (0.15f));
    g.drawRoundedRectangle (r, 3.0f, 1.0f);
}

void drawMeter (juce::Graphics& g, juce::Rectangle<float> r, float level)
{
    g.setColour (bg);
    g.fillRect (r);
    const float db = juce::Decibels::gainToDecibels (level, -60.0f);
    const float frac = juce::jlimit (0.0f, 1.0f, (db + 60.0f) / 66.0f);
    auto filled = r.withTop (r.getBottom() - r.getHeight() * frac);
    g.setGradientFill (juce::ColourGradient (play, r.getBottomLeft(), record, r.getTopLeft(), false));
    g.fillRect (filled);
}

} // namespace tessera::theme
