# Packaging

The AppImage contains an Ubuntu 22.04 runtime. The DEB and RPM wrap that same tested image, so applications do not depend on a distribution's SooperLooper version. Native wrappers extract the image into a versioned user cache to work without FUSE.

Build inside an Ubuntu 22.04 container with `packaging/Dockerfile.bundle`:

1. Run `python3 packaging/build_dsp.py`, then `python3 packaging/build_appdir.py`, then `python3 packaging/complete_manifest.py`.
2. Build the AppImage from `dist/TSMega-kit.AppDir` using the official [appimagetool](https://github.com/AppImage/appimagetool). Use `ARCH=x86_64` and name it `TSMega-kit-VERSION-x86_64.AppImage`.
3. Run `python3 packaging/build_native.py` to create the DEB and RPM.
4. Enable matching Ubuntu `deb-src` repositories and run `python3 packaging/download_runtime_sources.py` to collect corresponding runtime sources.
5. Test each artifact with `--self-test`, then check desktop integration and user-data preservation before publishing a tagged release.

Build outputs and downloaded tools are ignored by Git. ToneLib is downloaded by the end user from its official vendor, never included in a release. The local drum library, license registration and user loop/session audio are also excluded.
