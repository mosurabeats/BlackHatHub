cmake_minimum_required(VERSION 3.22)
project(Tessera VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_OSX_DEPLOYMENT_TARGET "11.0" CACHE STRING "Minimum macOS version")
if(APPLE AND NOT CMAKE_OSX_ARCHITECTURES)
    set(CMAKE_OSX_ARCHITECTURES "arm64;x86_64" CACHE STRING "Universal binary" FORCE)
endif()

# JUCE: uses a local checkout if JUCE_DIR is given, otherwise downloads the pinned release.
include(FetchContent)
if(DEFINED JUCE_DIR)
    add_subdirectory(${JUCE_DIR} juce EXCLUDE_FROM_ALL)
else()
    FetchContent_Declare(juce GIT_REPOSITORY https://github.com/juce-framework/JUCE.git GIT_TAG 8.0.4 GIT_SHALLOW TRUE)
    FetchContent_MakeAvailable(juce)
endif()

# ---------------------------------------------------------------- core library (model + engine, no GUI)
add_library(tessera_core STATIC
    Source/Model/Project.cpp
    Source/Model/ProjectController.cpp
    Source/Engine/AudioFileCache.cpp
    Source/Engine/Instruments.cpp
    Source/Engine/Effects.cpp
    Source/Engine/AudioEngine.cpp
    Source/Engine/Exporter.cpp)
target_include_directories(tessera_core PUBLIC Source)
target_compile_definitions(tessera_core PUBLIC
    JUCE_WEB_BROWSER=0 JUCE_USE_CURL=0 JUCE_MODAL_LOOPS_PERMITTED=1
    JUCE_DISPLAY_SPLASH_SCREEN=0 JUCE_STRICT_REFCOUNTEDPOINTER=1)
target_link_libraries(tessera_core
    PUBLIC juce::juce_audio_utils juce::juce_dsp juce::juce_audio_formats
           juce::juce_recommended_config_flags juce::juce_recommended_warning_flags)

# ---------------------------------------------------------------- desktop app
juce_add_gui_app(Tessera
    PRODUCT_NAME "Tessera"
    COMPANY_NAME "Tessera"
    BUNDLE_ID "com.tessera.daw"
    MICROPHONE_PERMISSION_ENABLED TRUE
    MICROPHONE_PERMISSION_TEXT "Tessera records audio from your inputs onto armed tracks.")
target_sources(Tessera PRIVATE
    Source/Main.cpp
    Source/UI/Theme.cpp
    Source/UI/TransportBar.cpp
    Source/UI/SessionView.cpp
    Source/UI/ArrangementView.cpp
    Source/UI/ClipEditor.cpp
    Source/UI/DeviceView.cpp
    Source/UI/BrowserView.cpp
    Source/UI/MainComponent.cpp)
target_link_libraries(Tessera PRIVATE tessera_core juce::juce_gui_extra)

# ---------------------------------------------------------------- tests (headless)
juce_add_console_app(TesseraTests PRODUCT_NAME "TesseraTests")
target_sources(TesseraTests PRIVATE Tests/TestMain.cpp Tests/EngineTests.cpp Tests/ModelTests.cpp)
target_link_libraries(TesseraTests PRIVATE tessera_core)

enable_testing()
add_test(NAME TesseraTests COMMAND TesseraTests)
