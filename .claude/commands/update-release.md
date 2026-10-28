Update the version and the docs together for: $ARGUMENTS

($ARGUMENTS = new version number, then what changed, e.g. `2.7.2 fix preview caption`. Patch for small changes, minor for features.)

1. Bump the version to the number given in $ARGUMENTS in every version file: @app.manifest (`X.Y.Z.0`), @installer.iss (AppVersion, AppVerName, OutputBaseFilename), @package_windows.bat (APP_VERSION), @pyproject.toml, @create_version_info.py, @src/__init__.py, @src/ui.py (`self.version`), the title and installer filename in @README.md, and line 7 of @CLAUDE.md. Afterwards grep for the old version to make sure none is left (ignore `build_env/`, `norm/` and the older sections of @ChangeLog.md).
2. Use the changelog-generator agent to update @ChangeLog.md, @README.md and @CLAUDE.md with the changes described in $ARGUMENTS. Follow norm/05-update-document.md: heading `## [version] - YYYY-MM-DD - title`, patch under 5 lines, minor under 10, major under 20.
3. Do not commit; report what changed.
