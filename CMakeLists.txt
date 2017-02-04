cmake_minimum_required(VERSION 2.8.9)

project(DeepInfer)

#-----------------------------------------------------------------------------
set(EXTENSION_HOMEPAGE "http://www.slicer.org/slicerWiki/index.php?title=Documentation/Nightly/Extensions/DeepInfer")
set(EXTENSION_CATEGORY "Machine Learning")
set(EXTENSION_CONTRIBUTORS "Alireza Mehrtash(UBC, BWH), Mehran Pesteie (UBC)")
set(EXTENSION_DESCRIPTION "Deep learning deployment toolkit for medical imaging.")
set(EXTENSION_ICONURL "https://www.slicer.org/w/images/a/a9/Deepinfer-256.png")
# set(EXTENSION_SCREENSHOTURLS "http://www.slicer.org/slicerWiki/images/b/bf/TCIABrowser-screenshot.png")

#-----------------------------------------------------------------------------
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
add_subdirectory(DeepInfer)

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_CPACK})
