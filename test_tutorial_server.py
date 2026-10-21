"""Browser-test launcher: exercise the folder action without opening native Explorer.
Started by test_tutorial_ui.mjs with a throwaway CLEANER_HOME. It is not a test on its own."""
import os
import sys

if __name__ == '__main__':
    if not os.environ.get('CLEANER_HOME'):
        sys.exit('This starts the app for test_tutorial_ui.mjs. Run that instead: it uses a throwaway CLEANER_HOME, not your real vault.')
    import app
    app.open_folder = lambda folder: None
    app.fathom.has_key = lambda: True  # simulate a connected account without reading credentials
    app.PRACTICE_HOME = app.clean.HOME.parent / (app.clean.HOME.name + '-practice')
    app.main()
