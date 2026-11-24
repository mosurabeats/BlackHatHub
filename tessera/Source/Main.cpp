#include "UI/MainComponent.h"

class TesseraApplication : public juce::JUCEApplication
{
public:
    const juce::String getApplicationName() override { return "Tessera"; }
    const juce::String getApplicationVersion() override { return "0.1.0"; }
    bool moreThanOneInstanceAllowed() override { return false; }

    void initialise (const juce::String& commandLine) override
    {
        mainWindow = std::make_unique<MainWindow> (getApplicationName());
        auto args = juce::StringArray::fromTokens (commandLine, true);
        if (args.contains ("--demo")) mainWindow->main->loadDemo();
        if (args.contains ("--arrangement")) mainWindow->main->showArrangement();
        // --screenshot <file.png>: render the window to an image and quit (used for CI smoke tests)
        const int si = args.indexOf ("--screenshot");
        if (si >= 0 && si + 1 < args.size())
        {
            const juce::File out (args[si + 1].unquoted());
            juce::Timer::callAfterDelay (2500, [this, out]
            {
                auto& c = mainWindow->main->context();
                juce::String want;
                if (int ti = juce::StringArray::fromTokens (juce::JUCEApplication::getCommandLineParameters(), true).indexOf ("--select"); ti >= 0)
                    want = juce::StringArray::fromTokens (juce::JUCEApplication::getCommandLineParameters(), true)[ti + 1];
                if (! c.project().tracks.empty())
                    for (auto& t : c.project().tracks)
                        for (int s = 0; s < (int) t.slots.size(); ++s)
                            if (t.slots[(size_t) s] && t.kind == tessera::TrackKind::midi && (want.isEmpty() || t.name == want)) { c.select (t.id, tessera::Selection::Where::slot, s); goto selected; }
                selected:
                juce::Timer::callAfterDelay (500, [this, out]
                {
                    auto img = mainWindow->main->createComponentSnapshot (mainWindow->main->getLocalBounds());
                    juce::FileOutputStream os (out);
                    if (os.openedOk()) { os.setPosition (0); os.truncate(); juce::PNGImageFormat().writeImageToStream (img, os); }
                    std::printf ("screenshot: %s\n", out.getFullPathName().toRawUTF8());
                    quit();
                });
            });
        }
    }

    void shutdown() override { mainWindow = nullptr; }

    void systemRequestedQuit() override
    {
        if (mainWindow == nullptr) { quit(); return; }
        mainWindow->main->confirmDiscard ([] { juce::JUCEApplication::getInstance()->quit(); });
    }

    void anotherInstanceStarted (const juce::String&) override {}

    class MainWindow : public juce::DocumentWindow
    {
    public:
        explicit MainWindow (const juce::String& name)
            : DocumentWindow (name, tessera::theme::bg, DocumentWindow::allButtons)
        {
            setUsingNativeTitleBar (true);
            main = new tessera::MainComponent();
            main->onTitleChange = [this] (const juce::String& t) { setName (t); };
            setContentOwned (main, true);
#if JUCE_MAC
            juce::MenuBarModel::setMacMainMenu (main);
#endif
            setResizable (true, true);
            setResizeLimits (980, 640, 10000, 10000);
            centreWithSize (getWidth(), getHeight());
            setVisible (true);
            main->grabKeyboardFocus();
        }

        ~MainWindow() override
        {
#if JUCE_MAC
            juce::MenuBarModel::setMacMainMenu (nullptr);
#endif
        }

        void closeButtonPressed() override { juce::JUCEApplication::getInstance()->systemRequestedQuit(); }
        tessera::MainComponent* main = nullptr;
    };

private:
    std::unique_ptr<MainWindow> mainWindow;
};

START_JUCE_APPLICATION (TesseraApplication)
